# Network Address, Bit String, and Built-in Geometric Types in PostgreSQL

In PostgreSQL, data goes beyond `INTEGER`, `TEXT`, `BOOLEAN`, and `TIMESTAMP`. The DBMS also provides **specialized data types** to store IP addresses, network ranges, hardware addresses, bit strings, and two-dimensional planar geometries. These types come with built-in validation rules, operators, and functions, making SQL queries reflect the true nature of the data far better than storing everything as `TEXT`.

For example, when storing IP addresses as strings, queries have to handle IPv4/IPv6 syntax and check whether an address belongs to `192.168.10.0/24` manually. With `inet` and `cidr`, PostgreSQL provides operators for that task. When storing eight feature flags in a bit string, `bit(8)` supports AND, OR, XOR, and bit-shifting operations. When managing `(x, y)` coordinates, the `point` type and geometric operators can compute Euclidean distance directly.

This lesson belongs to the **Data Types** chapter of the **Database Engine Relational PostgreSQL** module and covers three groups:

1. **Network types:** `inet`, `cidr`, `macaddr`, and `macaddr8`.
2. **Bit string types:** `bit(n)`, `bit varying(n)`, bitwise operators, and per-bit operations.
3. **Built-in geometric types:** `point`, `line`, `lseg`, `box`, `path`, `polygon`, and `circle`.

Beyond syntax, the lesson clarifies **storage semantics, validation, indexing, limitations, and type selection** for practical schema design. The examples use mock data or private/documentation network addresses; no Internet connection or real hardware is required.

> The geometric types in this chapter are **PostgreSQL's built-in types**, not `geometry`/`geography` from the PostGIS extension. They serve basic planar geometry calculations and **do not inherently understand geographic coordinate systems, SRIDs, meters, or distances on the Earth's surface**.

## 1. Why Choose Specialized Types Over TEXT?

Suppose we have an access log table:

~~~sql
CREATE TABLE access_log_text (
    log_id BIGINT PRIMARY KEY,
    client_ip TEXT NOT NULL
);
~~~

This table accepts both a valid address like `192.168.10.12` and non-IP strings like `hello-world`. To check which network an address belongs to, the application has to parse it manually or resort to complex string transformations.

An alternative design:

~~~sql
CREATE TABLE access_log_typed (
    log_id BIGINT PRIMARY KEY,
    client_ip INET NOT NULL
);
~~~

When an invalid address is inserted, PostgreSQL rejects it right at the data type boundary. At the same time:

~~~sql
SELECT
    log_id,
    client_ip
FROM access_log_typed
WHERE client_ip <<= CIDR '192.168.10.0/24';
~~~

is a clear, expressive SQL query: find IPs contained within or equal to the specified network range, following PostgreSQL network operator semantics.

Benefits of specialized types:

- **Format and domain validation** on data entry.
- **Clearer semantic expression** than a column name alone.
- **Dedicated operators** for cases unsuitable for string comparison.
- **Corresponding conversion and metadata query functions**.
- **Indexing support** for operations covered by operator classes.
- **Less custom parsing/comparison code** duplicated across applications.

However, specialized does not always mean better in every situation: for instance, `bit(8)` is hard to maintain if each bit carries undocumented secret business meaning; `point` is not enough to build a GIS system measuring distances in meters across the globe.

## 2. Overview of Types in This Lesson

| Type | Representation | Example | Typical Use Case |
|---|---|---|---|
| `inet` | IPv4/IPv6 address, optionally with prefix length | `192.168.10.15/24`, `2001:db8::1` | Client IP, host, endpoint |
| `cidr` | Normalized IPv4/IPv6 network block by prefix | `192.168.10.0/24` | ACLs, subnets, routing policies |
| `macaddr` | 48-bit MAC address | `08:00:2b:01:02:03` | Hardware identification on a suitable network |
| `macaddr8` | 64-bit MAC/EUI-64 identifier | `08:00:2b:ff:fe:01:02:03` | Hardware/EUI-64 address |
| `bit(n)` | String of exactly `n` bits | `B'10100101'` | Fixed bit flags, short binary codes |
| `bit varying(n)` | Bit string up to `n` bits long | `B'101'` | Variable-length bit strings |
| `point` | Planar coordinate `(x,y)` | `(3,4)` | Position on a 2D plane |
| `line` | Infinite line | `{1,-1,0}` | Relationships between lines |
| `lseg` | Line segment with two endpoints | `[(0,0),(3,4)]` | Path segment / linear boundary |
| `box` | Axis-aligned rectangle | `((0,0),(10,10))` | Bounding box, intersection checks |
| `path` | Sequence of points forming an open or closed path | `[(0,0),(2,2),(4,0)]` | Planar path |
| `polygon` | Planar polygon | `((0,0),(4,0),(4,3),(0,3))` | Simple geometric region |
| `circle` | Circle defined by center and radius | `<(0,0),5>` | Circular coverage area |

Values and notation in the table are examples only. When storing planar geometries, **coordinate units are defined by the application**, not inferred by PostgreSQL.

## 3. Preparing the Practice Environment

You need a PostgreSQL server and privileges to create schemas/tables in a **dedicated learning database**. You can connect using `psql`, pgAdmin, or any SQL client.

Check your environment:

~~~sql
SELECT
    version() AS postgres_version,
    current_database() AS database_name,
    current_user AS role_name;
~~~

In this lesson, we use the `typed_lab` schema to keep practice objects separate from other application tables:

~~~sql
CREATE SCHEMA typed_lab;
~~~

This statement is run once. If the schema already exists, PostgreSQL raises an error; do not drop a real schema just to redo the exercises. You can use a fresh lab database or choose a different schema name.

`SELECT` examples that use literals without tables can be run immediately. Table creation examples use fully qualified names such as `typed_lab.allowed_network` so they do not depend on `search_path`.

## 4. inet: IP Address Type with Optional Prefix

`inet` stores an IPv4 or IPv6 address along with an optional **network prefix length**.

Examples:

~~~sql
SELECT
    INET '192.168.10.15'       AS ipv4_host,
    INET '192.168.10.15/24'    AS ipv4_with_prefix,
    INET '2001:db8::1'        AS ipv6_host,
    INET '2001:db8::1/64'     AS ipv6_with_prefix;
~~~

For a host address written without a prefix, PostgreSQL assumes the full host mask: `/32` for IPv4 and `/128` for IPv6.

**Key point:** `inet` can store a host address **with non-zero host bits even when the prefix is shorter**. Thus `192.168.10.15/24` is a valid `inet` value containing both the host address and the prefix.

### 4.1. inet Is Not Just for IPv4

`inet` supports both IPv4 and IPv6 in the same column. An application can use:

~~~sql
CREATE TABLE typed_lab.access_event (
    event_id BIGINT PRIMARY KEY,
    remote_ip INET NOT NULL,
    event_name TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL
);
~~~

This avoids needing two separate columns `ipv4_address` and `ipv6_address` for one field with the same meaning ("client IP address").

However, some validation policies or indexes may still need to distinguish IPv4 vs. IPv6 using the `family()` function.

### 4.2. Valid and Invalid Values

Valid examples:

~~~sql
SELECT INET '10.20.30.40';
SELECT INET '2001:db8:0:1::1234';
~~~

Invalid examples—**do not run these together with a successful data-loading script**:

~~~sql
-- Expected error: IPv4 octet out of allowed range.
-- SELECT INET '192.168.10.999';

-- Expected error: not a valid IPv4/IPv6 address.
-- SELECT INET 'not-an-ip';
~~~

Whether PostgreSQL accepts a network literal also depends on the type's input syntax; applications should standardize on canonical input formats rather than inventing ad-hoc string slicing.

## 5. cidr: Type for Network Blocks

`cidr` represents a **network address** with a prefix length, where all host bits must conform to the network boundary.

Examples:

~~~sql
SELECT
    CIDR '192.168.10.0/24' AS office_subnet,
    CIDR '10.0.0.0/8'      AS private_subnet,
    CIDR '2001:db8::/32'  AS ipv6_documentation_network;
~~~

A `192.168.10.0/24` block covers IPv4 addresses whose first 24 bits match that network.

Difference from `inet`:

~~~sql
-- Valid because inet can hold a host address + prefix:
SELECT INET '192.168.10.15/24';

-- Invalid for cidr because host bits are non-zero:
-- SELECT CIDR '192.168.10.15/24';
~~~

PostgreSQL requires `cidr` values to match the network boundary; literals with non-zero host bits are rejected.

### 5.1. When to Use inet vs. cidr?

| Question | Prefer |
|---|---|
| "Which IP did this request originate from?" | `inet` |
| "Which IP does the server have on this interface?" | `inet` |
| "Which subnet is permitted access?" | `cidr` |
| "Which network block belongs to administrative zone A?" | `cidr` |
| "Need to store host and subnet mask together?" | `inet` |
| "Need to forbid storing a network block with non-zero host bits?" | `cidr` |

Do not store a `cidr` column named `client_ip` and use it as a host identifier if the application actually needs to distinguish individual addresses within the same network.

### 5.2. Prefix Length Is Not Octet Count

IPv4 has 32 bits; `/24` means the first 24 bits belong to the prefix, not 24 bytes. IPv6 has 128 bits; `/64` means the first 64 bits.

~~~text
IPv4: 192.168.10.15/24
      11000000 10101000 00001010 | 00001111
      <-------- 24 bits ---------> | <-8 bits->

CIDR network: 192.168.10.0/24

IPv6: 2001:db8::1/64
      64-bit prefix inside a 128-bit address
~~~

Do not attempt to split addresses on dots to handle IPv6; IPv6 formatting allows several valid compressed representations.

## 6. Network Address Functions

PostgreSQL provides functions that operate directly on `inet`/`cidr`.

### 6.1. host(), network(), masklen(), family()

~~~sql
SELECT
    host(INET '192.168.10.15/24') AS host_text,
    network(INET '192.168.10.15/24') AS network_part,
    masklen(INET '192.168.10.15/24') AS prefix_length,
    family(INET '192.168.10.15/24') AS address_family;
~~~

Meaning:

- `host()` returns the host address portion as text in the function's representation format.
- `network()` returns the corresponding network address for the prefix.
- `masklen()` returns the prefix length.
- `family()` indicates the address family: `4` for IPv4, `6` for IPv6.

Expected values: host is `192.168.10.15`, network is `192.168.10.0/24`, mask length is `24`, address family is `4`.

### 6.2. broadcast(), netmask(), hostmask()

~~~sql
SELECT
    broadcast(INET '192.168.10.15/24') AS broadcast_address,
    netmask(INET '192.168.10.15/24') AS subnet_mask,
    hostmask(INET '192.168.10.15/24') AS host_mask;
~~~

For an IPv4 `/24`, the corresponding values show the network in familiar terms: broadcast address `192.168.10.255`, subnet mask `255.255.255.0`, and host mask `0.0.0.255`.

Do not assume IPv4 broadcast concepts behave identically in IPv6; the address functions are defined at the data type level, whereas actual networking semantics differ.

### 6.3. inet_same_family() and inet_merge()

~~~sql
SELECT
    inet_same_family(
        INET '192.168.1.10',
        INET '192.168.2.20'
    ) AS same_ip_family;

SELECT
    inet_merge(
        INET '192.168.10.0/24',
        INET '192.168.11.0/24'
    ) AS covering_network;
~~~

`inet_same_family` checks whether two addresses belong to the same IPv4/IPv6 family. `inet_merge` produces the smallest CIDR range covering both input ranges, which is useful when analyzing network rules.

**Be careful:** the smallest covering range may include additional IPs outside the original two subnets. Never automatically merge ACL policies just because two prefixes look adjacent; always check security implications.

## 7. Network Containment Operators

Network operators let you check address ranges without manual bit manipulation.

| Operator | Basic Meaning |
|---|---|
| `<<` | Left operand is **strictly contained within** right operand |
| `<<=` | Left operand is **contained within or equal to** right operand |
| `>>` | Left operand **strictly contains** right operand |
| `>>=` | Left operand **contains or equals** right operand |
| `&&` | The two address ranges overlap |
| `=`, `<>` | Equality/inequality comparison per network type semantics |
| `<`, `<=`, `>`, `>=` | Ordering comparison defined by PostgreSQL for network types |

Examples:

~~~sql
SELECT
    INET '192.168.10.15' << CIDR '192.168.10.0/24'
        AS host_strictly_inside,

    INET '192.168.10.15' <<= CIDR '192.168.10.0/24'
        AS host_inside_or_equal,

    CIDR '192.168.10.0/24' >>= INET '192.168.10.15'
        AS subnet_contains_host,

    CIDR '192.168.10.0/24' && CIDR '192.168.10.128/25'
        AS ranges_overlap;
~~~

All checks above evaluate to **TRUE** under the corresponding containment/coverage definitions.

### 7.1. Distinguishing << from <<=
 
~~~sql
SELECT
    CIDR '10.20.0.0/16' << CIDR '10.20.0.0/16'
        AS strict_containment,

    CIDR '10.20.0.0/16' <<= CIDR '10.20.0.0/16'
        AS inclusive_containment;
~~~

Two equal blocks do **not** satisfy strict containment (`<<`), but do satisfy contained-or-equal (`<<=`).

When writing ACLs or subnet checks, picking the wrong operator between these two can silently exclude valid matches.

### 7.2. Do Not Confuse Comparison Order with Network "Proximity"

Ordering operators on `inet`/`cidr` serve PostgreSQL sorting rules; they **do not represent network distance or optimal routing**.

To test whether an address belongs to a subnet, use containment operators. To prioritize multiple matching routes, define an explicit policy such as **longest prefix match** rather than just `ORDER BY remote_ip`.

## 8. Designing Subnet and Access Address Tables

Create a table of allowed network ranges:

~~~sql
CREATE TABLE typed_lab.allowed_network (
    network_id INTEGER PRIMARY KEY,
    network_name TEXT NOT NULL,
    network_block CIDR NOT NULL UNIQUE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO typed_lab.allowed_network
    (network_id, network_name, network_block)
VALUES
    (1, 'Office', CIDR '192.168.10.0/24'),
    (2, 'Office management', CIDR '192.168.10.128/25'),
    (3, 'Internal services', CIDR '10.20.0.0/16'),
    (4, 'IPv6 lab', CIDR '2001:db8:100::/48');

INSERT INTO typed_lab.access_event
    (event_id, remote_ip, event_name, observed_at)
VALUES
    (1001, INET '192.168.10.15', 'login',
        TIMESTAMPTZ '2026-03-01 08:00:00+00'),
    (1002, INET '192.168.10.200', 'read',
        TIMESTAMPTZ '2026-03-01 08:10:00+00'),
    (1003, INET '10.20.1.9', 'write',
        TIMESTAMPTZ '2026-03-01 08:20:00+00'),
    (1004, INET '2001:db8:100::8', 'login',
        TIMESTAMPTZ '2026-03-01 08:30:00+00'),
    (1005, INET '203.0.113.22', 'read',
        TIMESTAMPTZ '2026-03-01 08:40:00+00');
~~~

The networks used in this example include private and documentation ranges. They are not security policies to be copied directly into production.

### 8.1. Finding Logs Belonging to a Subnet

~~~sql
SELECT
    event_id,
    remote_ip,
    event_name
FROM typed_lab.access_event
WHERE remote_ip <<= CIDR '192.168.10.0/24'
ORDER BY event_id;
~~~

This returns events `1001` and `1002`.

### 8.2. Joining IPs Against Allowed Networks

~~~sql
SELECT
    e.event_id,
    e.remote_ip,
    n.network_name,
    n.network_block
FROM typed_lab.access_event AS e
JOIN typed_lab.allowed_network AS n
    ON e.remote_ip <<= n.network_block
WHERE n.enabled = TRUE
ORDER BY e.event_id, n.network_id;
~~~

One IP can match **multiple nested networks**. For example, `192.168.10.200` falls inside both `192.168.10.0/24` and `192.168.10.128/25`. As a result, the JOIN can produce multiple rows for the same event.

If business logic needs **a single preferred match** instead of all matching subnets, an explicit tie-breaking rule must be defined.

### 8.3. Longest Prefix Match with LATERAL

~~~sql
SELECT
    e.event_id,
    e.remote_ip,
    matched.network_name,
    matched.network_block
FROM typed_lab.access_event AS e
LEFT JOIN LATERAL (
    SELECT
        n.network_name,
        n.network_block
    FROM typed_lab.allowed_network AS n
    WHERE n.enabled = TRUE
      AND e.remote_ip <<= n.network_block
    ORDER BY
        masklen(n.network_block) DESC,
        n.network_id
    LIMIT 1
) AS matched ON TRUE
ORDER BY e.event_id;
~~~

Explanation:

- `LATERAL` allows the subquery to reference `e.remote_ip` from each outer row.
- `masklen DESC` prioritizes longer prefixes, corresponding to more specific networks.
- `n.network_id` provides deterministic ordering if multiple records share the same prefix length.
- `LEFT JOIN` retains events that do not belong to any enabled subnet.

In real firewall/router applications, many additional policy factors apply, such as deny/allow priority, direction, protocol, and default deny. **Longest prefix match is just one network selection rule**, not a replacement for a full policy engine.

## 9. Indexing inet and cidr

PostgreSQL supports multiple index access methods and operator classes. Index selection must be based on **query operators** and the actual PostgreSQL version.

For equality or sorting lookups by IP:

~~~sql
CREATE INDEX idx_access_event_ip
ON typed_lab.access_event (remote_ip);
~~~

This is a standard B-tree index. It helps conditions such as `remote_ip = INET '192.168.10.15'` when data volume and selectivity make the planner favor it.

For `inet`/`cidr` containment queries, specialized operator classes on **SP-GiST or GiST** may be suitable on supporting versions. Example of an option to evaluate:

~~~sql
-- Use on PostgreSQL versions with a matching SP-GiST opclass.
CREATE INDEX idx_allowed_network_spgist
ON typed_lab.allowed_network
USING spgist (network_block);
~~~

Do not assume every index supports every operator; verify the operator classes on your running server and inspect `EXPLAIN`.

~~~sql
EXPLAIN
SELECT event_id
FROM typed_lab.access_event
WHERE remote_ip <<= CIDR '192.168.10.0/24';
~~~

On a sample table with just a few rows, a sequential scan can be optimal and **does not prove the index is broken**. Evaluating indexes properly requires representative row counts, network distributions, and query patterns.

### 9.1. Notes on Network Data and Privacy

IP addresses can be considered user-related data depending on context. When storing them:

- Only retain what is necessary for operational purposes.
- Define appropriate retention periods.
- Restrict who can read IP logs.
- Do not rely on IP addresses as permanent user identities.
- Account for NAT, proxies, IPv6 privacy addresses, and client-supplied headers.

If the system sits behind a reverse proxy, the real client IP must be determined from a **trusted proxy chain and network configuration**, not by trusting an arbitrary client-supplied header as authoritative evidence.

## 10. macaddr: 48-Bit Hardware Addresses

`macaddr` stores a 6-byte (48-bit) MAC address, commonly written as six hexadecimal pairs.

Example:

~~~sql
SELECT
    MACADDR '08:00:2b:01:02:03' AS device_mac,
    MACADDR '08-00-2b-01-02-03' AS same_device_form;
~~~

PostgreSQL accepts several valid input formats and normalizes values to the type's standard output format.

Important considerations:

- `macaddr` provides domain validation and comparisons dedicated to hardware addresses.
- A MAC address is not an IP address.
- MAC addresses are link-layer information, not Internet-routable addresses like IPv4/IPv6.
- MAC addresses can be changed, spoofed, or randomized by devices/operating systems.
- Never use a MAC address alone as proof of user or device authentication.

Example table storing devices in an internal management system:

~~~sql
CREATE TABLE typed_lab.device (
    device_id BIGINT PRIMARY KEY,
    asset_name TEXT NOT NULL,
    hardware_address MACADDR,
    feature_flags BIT(8) NOT NULL DEFAULT B'00000000',
    location_2d POINT
);

INSERT INTO typed_lab.device
    (device_id, asset_name, hardware_address, feature_flags, location_2d)
VALUES
    (
        201, 'Switch A',
        MACADDR '08:00:2b:01:02:03',
        B'10000100',
        point(2, 3)
    ),
    (
        202, 'Sensor B',
        MACADDR '02:11:22:33:44:55',
        B'01000001',
        point(7, 9)
    );
~~~

The `location_2d` column here is merely a planar coordinate on a hypothetical building floorplan, **not longitude/latitude or a real map**.

## 11. macaddr8: 64-Bit Hardware/EUI-64 Addresses

`macaddr8` represents an 8-byte (64-bit) hardware identifier, commonly used in EUI-64 contexts.

~~~sql
SELECT
    MACADDR8 '08:00:2b:ff:fe:01:02:03'
        AS eui64_sample;
~~~

PostgreSQL can accept certain 6-byte inputs and convert them according to `macaddr8` rules, but **you should not treat every 48-bit and 64-bit sequence as the same physical identifier** without a defined normalization policy.

Comparison table:

| Criterion | macaddr | macaddr8 |
|---|---|---|
| Identifier length | 48 bits | 64 bits |
| Example representation | `08:00:2b:01:02:03` | `08:00:2b:ff:fe:01:02:03` |
| Purpose | MAC/EUI-48 | EUI-64 or corresponding representation |
| Replaces inet/cidr? | No | No |
| Sufficient for identity authentication? | No | No |

If an application does not manage actual MAC/EUI-64 identifiers, do not add a `macaddr` column just to "have another network address." A remote website visitor's MAC address is normally **unavailable** at the standard HTTP layer.

## 12. Bit Strings: How Does a Bit String Differ from an Integer?

PostgreSQL provides **bit string** types to store sequences of 0/1 values.

Example:

~~~sql
SELECT
    B'1010' AS bits_4,
    B'00001111' AS bits_8,
    X'AF' AS bits_from_hex;
~~~

Literals:

- `B'1010'` is a 4-bit binary literal.
- `X'AF'` is a hexadecimal literal representing the corresponding bits.
- `bit` and `varbit` are bit string types, not standard integer types.

Bit strings differ from integers in that **length and bit position are part of their essential semantics**. For example, `B'0010'` has 4 bits; the integer 2 does not preserve the fact that there are two leading zero bits.

Typical uses:

- Feature flags with fixed bit positions.
- Protocol bitmap fields.
- Short bit patterns in technical data.
- Fixed-format encoded outputs from an algorithm.
- Device status indicators mapped to specific bits.

For a handful of independent business attributes, separate `BOOLEAN` columns are often easier to read and query than a bitmap.

## 13. bit(n): Strings of Exactly n Bits

`BIT(n)` requires a value of exact length `n` bits under assignment rules.

Example:

~~~sql
CREATE TABLE typed_lab.bit_demo (
    demo_id INTEGER PRIMARY KEY,
    status_mask BIT(8) NOT NULL
);

INSERT INTO typed_lab.bit_demo
    (demo_id, status_mask)
VALUES
    (1, B'00001111'),
    (2, B'10101010');
~~~

A `BIT(8)` value has 8 bit positions; both `00001111` and `10101010` are valid.

### 13.1. Values Shorter or Longer Than the Declared Length

Assigning a bit string that does not match the column length can be rejected:

~~~sql
-- Example that fails because length does not match BIT(8):
-- INSERT INTO typed_lab.bit_demo VALUES (3, B'101');

-- Example that fails because it has more than 8 bits:
-- INSERT INTO typed_lab.bit_demo VALUES (4, B'101010101');
~~~

When **explicitly casting** to `bit(n)`, PostgreSQL follows specific rules to **zero-pad on the right or truncate excess bits on the right**:

~~~sql
SELECT
    B'101'::BIT(8) AS explicitly_padded,
    B'110011001'::BIT(8) AS explicitly_truncated;
~~~

The resulting values under cast rules are 8-bit strings. This differs from assuming "casting will always raise an error if the length is wrong."

**Because casting can silently lose information**, do not blindly cast mismatched inputs just to suppress errors. For protocol data, verify length and padding rules upfront.

### 13.2. Can You Omit n?

In PostgreSQL, `BIT` without a specified length defaults to **1 bit**. Therefore, if you need an 8-bit flag mask, write `BIT(8)` explicitly.

Do not assume `BIT` without a length stores arbitrarily long bit strings. For that, you need `BIT VARYING`.

## 14. bit varying(n) and varbit(n): Variable Length

`BIT VARYING(n)`, often written `VARBIT(n)`, allows lengths from 0 up to `n` bits under the corresponding limit.

Example:

~~~sql
CREATE TABLE typed_lab.bit_payload (
    payload_id INTEGER PRIMARY KEY,
    bit_payload BIT VARYING(16) NOT NULL
);

INSERT INTO typed_lab.bit_payload
    (payload_id, bit_payload)
VALUES
    (1, B'1'),
    (2, B'101010'),
    (3, B'0000000011111111');
~~~

These rows have different lengths, all within 16 bits.

If you need variable length with no upper bound specified, PostgreSQL supports `BIT VARYING` without `n` subject to general system limits.

### 14.1. When Should You Use BIT VARYING?

- Data length itself carries important information.
- Short payloads do not need to be padded to a fixed width.
- Different rows have different bit counts in the same column.
- Processing rules clearly define permitted lengths.

If every record must store an exact 8-bit bitmap, `BIT(8)` expresses that constraint much more clearly in the schema.

### 14.2. BIT VARYING Does Not Replace BYTEA

`BYTEA` stores binary byte strings; `BIT VARYING` stores bit strings whose length does not have to be a multiple of 8.

When handling files or large byte-aligned binary payloads, `BYTEA` is usually more suitable. When you need **5 or 13 bits** specifically, a bit string expresses bit-level length naturally.

Do not pick `VARBIT` merely because data is "binary." Consider the operations you need and driver/application ecosystem support.

## 15. Bitwise Operators in PostgreSQL

Common operators:

| Operator | Meaning | Example |
|---|---|---|
| `&` | Bitwise AND | `B'1010' & B'1100'` |
| `\|` | Bitwise OR | `B'1010' \| B'1100'` |
| `#` | Bitwise XOR | `B'1010' # B'1100'` |
| `~` | Bitwise NOT (invert each bit) | `~ B'1010'` |
| `<<` | Shift left, preserving bit string length | `B'1010' << 1` |
| `>>` | Shift right, preserving bit string length | `B'1010' >> 2` |
| `\|\|` | Concatenate two bit strings | `B'10' \|\| B'01'` |

Results:

~~~sql
SELECT
    B'1010' & B'1100' AS and_bits,       -- 1000
    B'1010' | B'1100' AS or_bits,        -- 1110
    B'1010' # B'1100' AS xor_bits,       -- 0110
    ~ B'1010' AS not_bits,              -- 0101
    B'1010' << 1 AS shifted_left,        -- 0100
    B'1010' >> 2 AS shifted_right,       -- 0010
    B'10' || B'01' AS concatenated_bits; -- 1001
~~~

**Length matters:** for binary bitwise operators such as AND/OR/XOR, both bit string operands must have matching lengths. Do not assume PostgreSQL automatically pads strings of different lengths.

### 15.1. The << Operator Differs Between Network and Bit Types

In the network section:

~~~sql
SELECT INET '192.168.10.15' << CIDR '192.168.10.0/24';
~~~

`<<` means **strictly contained within the network**.

In the bit section:

~~~sql
SELECT B'1010' << 1;
~~~

`<<` means **shift the bit string left**.

PostgreSQL selects operator semantics based on **operand types**. This illustrates why data types are part of SQL semantics, not just byte storage layouts.

## 16. Functions for Working with Bit Strings

### 16.1. bit_length() and octet_length()

~~~sql
SELECT
    bit_length(B'10101') AS number_of_bits,
    octet_length(B'10101') AS storage_bytes_for_value;
~~~

`bit_length` returns the number of significant bits in the string. `octet_length` reports the byte count according to the function's representation measurement; do not assume that figure equals the total tuple and index storage cost in PostgreSQL.

### 16.2. get_bit() and set_bit()

~~~sql
SELECT
    get_bit(B'1010', 0) AS first_bit,
    get_bit(B'1010', 1) AS second_bit,
    set_bit(B'1010', 1, 1) AS new_bit_string;
~~~

For bit strings, position `0` is the **leftmost** bit. Therefore:

- `get_bit(B'1010', 0)` returns `1`.
- `get_bit(B'1010', 1)` returns `0`.
- `set_bit(B'1010', 1, 1)` produces `B'1110'`.

Out-of-bounds positions raise an error; the new bit value must be 0 or 1. Maintain a documented table describing each bit position instead of keeping bit meanings solely in developers' heads.

### 16.3. bit_count()

In PostgreSQL versions that support `bit_count`, you can count the number of 1 bits:

~~~sql
SELECT bit_count(B'101101') AS one_bits;
~~~

The sample value has four 1 bits. If targeting older PostgreSQL releases, check function availability before relying on it in portable SQL; do not assume every release shares the exact same function list.

## 17. Designing Feature Flags with BIT(8)

In `typed_lab.device`, we have:

~~~sql
feature_flags BIT(8) NOT NULL DEFAULT B'00000000'
~~~

Suppose the convention is:

~~~text
Bit positions (from left, 0-based):

  0 1 2 3 4 5 6 7
  | | | | | | | |
  | | | | | | | +-- experimental
  | | | | | | +---- reporting enabled
  | | | | | +------ calibrated
  | | | | +-------- reserved
  | | | +---------- reserved
  | | +------------ internal GPS
  | +-------------- alerts enabled
  +---------------- monitoring enabled
~~~

This mapping is purely illustrative for the lab; in a real application, every bit needs **stable documentation and version compatibility**.

### 17.1. Checking a Flag

~~~sql
SELECT
    device_id,
    asset_name,
    get_bit(feature_flags, 0) = 1 AS monitoring_enabled,
    get_bit(feature_flags, 1) = 1 AS alerts_enabled
FROM typed_lab.device
ORDER BY device_id;
~~~

Reading behavior: position 0 is the leftmost bit, so device 201 has monitoring enabled when `feature_flags = B'10000100'`.

### 17.2. Enabling a Flag with OR

~~~sql
UPDATE typed_lab.device
SET feature_flags = feature_flags | B'01000000'
WHERE device_id = 201
RETURNING device_id, feature_flags;
~~~

The mask `B'01000000'` turns on bit 1 from the left. OR preserves all other already-set bits.

### 17.3. Disabling a Flag with AND NOT

~~~sql
UPDATE typed_lab.device
SET feature_flags = feature_flags & ~ B'01000000'
WHERE device_id = 201
RETURNING device_id, feature_flags;
~~~

Bit 1 is reset to 0; all other bits are kept according to the mask. Both operands are 8 bits long.

### 17.4. Why Updating Directly in SQL Beats Ad-Hoc Read-Modify-Write

An application might:

1. `SELECT feature_flags`.
2. Compute the new bitmap in Java.
3. `UPDATE` the entire bitmap.

If two transactions concurrently compute updates from the same stale value, one transaction can overwrite the other's change.

For toggling individual bits, writing directly:

~~~sql
UPDATE typed_lab.device
SET feature_flags = set_bit(feature_flags, 0, 1)
WHERE device_id = 201;
~~~

updates based on the row's current value inside the statement, coordinated with PostgreSQL row locking. However, you still need proper transaction and concurrency design if multiple flags have interrelated constraints or require pre-update business checks.

## 18. Should Business States Be Stored as Bitmasks?

There are three common options:

**Multiple BOOLEAN columns:**

~~~sql
CREATE TABLE feature_boolean_demo (
    device_id BIGINT PRIMARY KEY,
    monitoring_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    alerts_enabled BOOLEAN NOT NULL DEFAULT FALSE
);
~~~

**One BIT(8) column:**

~~~sql
CREATE TABLE feature_bit_demo (
    device_id BIGINT PRIMARY KEY,
    feature_flags BIT(8) NOT NULL DEFAULT B'00000000'
);
~~~

**Relational feature table:**

~~~sql
CREATE TABLE device_feature_demo (
    device_id BIGINT NOT NULL,
    feature_code TEXT NOT NULL,
    PRIMARY KEY (device_id, feature_code)
);
~~~

| Criterion | BOOLEAN columns | BIT(n) | Relational table |
|---|---|---|---|
| SQL readability | High | Requires knowing bit positions | High with JOINs |
| Adding new features | May require ALTER TABLE | Easy if spare bits remain, hard when full | Usually insert new rows |
| Per-feature constraints | Easy to constrain | Requires expressions/logic | Flexible with metadata |
| Querying by feature name | Direct | Requires mask/`get_bit` | By `feature_code` |
| Bitmap protocol compatibility | Requires conversion | Native | Requires encoding |
| Changing number of features | Awkward if very numerous | Limited by size/mapping | Best fit when numerous and dynamic |

**Design recommendation:** use `BIT(n)` when bit meanings are **fixed, well-documented, or tied to a format/protocol**. For business states that are frequently added/removed and need readable queries, BOOLEAN columns or a relational model are usually easier to maintain.

## 19. Common Pitfalls with Bit Types

### 19.1. Confusing Length with Numeric Value

`B'0001'` and `B'1'` have different lengths. Do not treat them as equal simply because both represent the value 1 if converted to an integer.

### 19.2. Computing Masks with Inconsistent Bit Numbering

Some protocols number bit 0 as the rightmost bit, whereas `get_bit` on PostgreSQL bit strings indexes from the left. If a Java application uses integer bit-shifts, explicitly define **bit numbering** when converting between the two representations.

### 19.3. Mixing & with Boolean Expressions

~~~sql
-- Correct query example on BIT(8):
SELECT *
FROM typed_lab.device
WHERE (feature_flags & B'10000000') = B'10000000';
~~~

`&` returns a bit string, not a BOOLEAN. Comparing the result against the mask produces the boolean `WHERE` predicate.

### 19.4. Confusing BIT(n) with Unsigned Integer Bounds

`BIT(8)` is an 8-bit string, not automatically an integer 0–255 in every expression. When you need integer arithmetic and integer bitwise operations, integer types can fit better; when you need a fixed-position bit string, use BIT.

## 20. Built-in Geometric Types: Purpose and Scope

PostgreSQL provides **two-dimensional planar** geometric types:

~~~text
point   : a point (x, y)
line    : an infinitely extending line
lseg    : a finite line segment between two endpoints
box     : a rectangle defined by two corners
path    : a sequence of connected points, open or closed
polygon : a polygonal region
circle  : a circle/disk defined by center and radius
~~~

These types use PostgreSQL's built-in geometric representations and operators.

**Limitations to keep in mind:**

- No geographic coordinate system / SRID is automatically stored alongside them.
- Basic distance calculations are **Euclidean in a planar coordinate system**.
- Length/area units are defined by the application.
- Earth curvature and surface distortion are not handled.
- They do not replace PostGIS for most professional GIS workloads.
- Check index/operator class support per type; do not assume all types behave identically.

A warehouse floorplan measured in meters can use `point`. A system computing real travel distances between cities from longitude/latitude **should not** directly compute Euclidean distance between pairs of degree coordinates.

## 21. point: A Planar Coordinate (x, y)

`point` represents a two-dimensional point.

~~~sql
SELECT
    POINT '(3,4)' AS p1,
    point(3, 4) AS p2;
~~~

You can use a typed literal or construct it from two numbers.

Example sensor table:

~~~sql
CREATE TABLE typed_lab.sensor (
    sensor_id INTEGER PRIMARY KEY,
    sensor_name TEXT NOT NULL,
    position POINT NOT NULL,
    coverage CIRCLE,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO typed_lab.sensor
    (sensor_id, sensor_name, position, coverage)
VALUES
    (
        301, 'Sensor near gate',
        point(2, 3),
        circle(point(2, 3), 5)
    ),
    (
        302, 'Sensor in warehouse',
        point(8, 6),
        circle(point(8, 6), 4)
    ),
    (
        303, 'Sensor in corridor',
        point(12, 2),
        circle(point(12, 2), 3)
    );
~~~

In this example, coordinates represent arbitrary planar units, such as meters on a defined floorplan grid. Do not treat this data as real GPS coordinates.

### 21.1. Computing Distance Between Two Points

PostgreSQL supports the distance operator `<->` for `point`:

~~~sql
SELECT
    point(0, 0) <-> point(3, 4)
        AS planar_distance;
~~~

In planar geometry:

\[
d=\sqrt{(x_2-x_1)^2+(y_2-y_1)^2}
\]

For `(0,0)` and `(3,4)`, the result is **5** coordinate units.

Example finding sensors near an observation point:

~~~sql
SELECT
    sensor_id,
    sensor_name,
    position,
    position <-> point(5, 5) AS distance_units
FROM typed_lab.sensor
WHERE active = TRUE
ORDER BY
    position <-> point(5, 5),
    sensor_id
LIMIT 3;
~~~

The returned distance is measured **on the application's 2D plane**. If the coordinates are degrees of longitude/latitude, that number is **not a distance in meters**.

### 21.2. Point Arithmetic Does Not Model Routing Paths

A `point` is only a coordinate. It knows nothing about blocked corridors, obstacles, or actual travel routes. Two points may be close in a straight line yet far apart in walking distance; a routing graph or pathfinding algorithm is needed if the application requires navigation.

## 22. line and lseg: Infinite Line vs. Finite Segment

**`line`** represents an infinite line in the plane.

**`lseg`** represents a line segment between two endpoints.

Examples:

~~~sql
SELECT
    LINE '{1,-1,0}' AS diagonal_line,
    LSEG '[(0,0),(3,4)]' AS finite_segment;
~~~

For a line, the coefficient form corresponds to the equation:

\[
Ax+By+C=0
\]

For example, `{1,-1,0}` represents the line `x-y=0`.

For the segment `[(0,0),(3,4)]`, the two endpoints are (0,0) and (3,4), and the segment length is 5 units.

~~~sql
SELECT
    length(LSEG '[(0,0),(3,4)]')
        AS segment_length;
~~~

### 22.1. When to Use line vs. lseg?

- `line`: modeling directional relationships or an infinitely extending line.
- `lseg`: a bounded segment from A to B.
- `path`: multiple consecutive segments connecting a series of points.
- `polygon`: a closed region with interior semantics defined by the type.

A route passing through 10 points should not be forced into a single `lseg`, as that drops all intermediate points.

## 23. box: Axis-Aligned Rectangle

`box` is a rectangle defined by two opposite corners, with sides parallel to the coordinate axes.

~~~sql
SELECT
    box(point(0, 0), point(10, 10))
        AS room_box;
~~~

Example area calculation:

~~~sql
SELECT
    area(
        box(point(0, 0), point(10, 10))
    ) AS box_area;
~~~

The result is **100 square units**.

### 23.1. Checking Whether a Point Is Inside a Box

~~~sql
SELECT
    box(point(0, 0), point(10, 10))
        @> point(3, 4) AS contains_point;
~~~

The `@>` operator expresses **containment** for geometric types supporting that operand combination.

### 23.2. Checking Whether Two Boxes Overlap

~~~sql
SELECT
    box(point(0, 0), point(10, 10))
        && box(point(8, 8), point(15, 15))
        AS boxes_overlap;
~~~

The two boxes share an intersecting region, so the result is TRUE.

Do not assume "overlap" works identically across arbitrary pairs of geometric types: built-in geometric operators have **specific supported signatures** that must be checked against your PostgreSQL documentation and version.

### 23.3. What Problems Suit box?

- Simple bounding region checks.
- Preliminary filtering of locations or objects inside a rectangle.
- Storing 2D bounding boxes of objects.
- Reducing the number of expensive geometric checks when an application manages many objects.

PostgreSQL's `box` does not natively model rectangles rotated at an angle to the axes; for rotated objects, an axis-aligned bounding box may be larger than the actual shape.

## 24. path: A Route Through Multiple Points

`path` is a sequence of connected points. PostgreSQL distinguishes **open paths** and **closed paths**.

Example:

~~~sql
SELECT
    PATH '[(0,0),(2,2),(4,0)]'
        AS open_path,

    PATH '((0,0),(2,2),(4,0))'
        AS closed_path;
~~~

In standard literal syntax:

- Square brackets `[ ... ]` denote an open path.
- Outer parentheses `( ... )` denote a closed path.

You can check whether a path is open or closed:

~~~sql
SELECT
    isopen(PATH '[(0,0),(2,2),(4,0)]')
        AS open_flag,

    isclosed(PATH '((0,0),(2,2),(4,0))')
        AS closed_flag;
~~~

A **closed** path is not automatically equivalent to a polygon across all operators and indexes. `path` describes a connected polyline through points; `polygon` models a planar region.

### 24.1. Storing Paths in Practice

If an application stores multi-point routes, decide:

- Do all routes share the same coordinate system?
- Do you need to store individual segment lengths?
- Do you need to query constituent waypoints independently?
- Do you need route-intersection queries or distance-to-route queries?
- Do you need PostGIS or a road-network graph model instead?

Do not pick `path` just because data has multiple coordinates; sometimes a child table of points with `sequence_no` is easier to update and query per leg.

## 25. polygon: Two-Dimensional Polygonal Regions

`polygon` represents a planar polygon by its list of vertices.

~~~sql
SELECT
    POLYGON '((0,0),(4,0),(4,3),(0,3))'
        AS rectangle_polygon;
~~~

Example area calculation:

~~~sql
SELECT
    area(
        POLYGON '((0,0),(4,0),(4,3),(0,3))'
    ) AS polygon_area;
~~~

The rectangle has width 4 and height 3, so its area is **12 square units**.

### 25.1. Difference Between box and polygon

- `box` is always an axis-aligned rectangle defined by two corners.
- `polygon` can have many vertices and represent non-rectangular regions.
- `box` fits bounding boxes and simple filtering checks.
- `polygon` is more flexible for arbitrary boundary shapes within the semantics supported by the type.

For real geographic regions, a planar polygon is not enough to know the coordinate system, units, map projection, and Earth curvature. Use proper GIS tooling when the problem requires it.

### 25.2. Polygon Data Quality

Before relying on `polygon` for critical business decisions, the application should verify:

- Is vertex ordering correct?
- Do edges self-intersect?
- Are boundary points considered inside the region?
- Do all coordinates share the same unit?
- Are holes, multi-part disjoint regions, or complex topology needed?

Advanced requirements like polygons with holes, normalized topology validation, or deep geographic operations typically require PostGIS. Do not treat PostgreSQL's ability to parse a `polygon` literal as proof that the region satisfies all application geometry rules.

## 26. circle: Center and Radius

`circle` represents a circle/circular region by center and radius in a planar coordinate system.

~~~sql
SELECT
    CIRCLE '<(0,0),5>' AS circle_literal,
    circle(point(0, 0), 5) AS circle_constructed;
~~~

A circle centered at (0,0) with radius 5 is represented far more cleanly with `circle` than by approximating it with many polygon vertices.

Example circle area calculation:

~~~sql
SELECT
    area(circle(point(0, 0), 5))
        AS circle_area;
~~~

Mathematically:

\[
A=\pi r^2
\]

with `r=5`, the area is approximately `78.54` square units. This is a floating-point approximation, not exact financial accounting arithmetic.

### 26.1. Checking Whether a Point Lies Inside a Circle

~~~sql
SELECT
    circle(point(0, 0), 6) @> point(3, 4)
        AS contains_point;
~~~

The distance from the center to the point is 5, which is less than radius 6, so the result is TRUE.

### 26.2. Finding Sensors Covering a Location

~~~sql
SELECT
    sensor_id,
    sensor_name,
    coverage
FROM typed_lab.sensor
WHERE active = TRUE
  AND coverage @> point(5, 5)
ORDER BY sensor_id;
~~~

Here `coverage` is a hypothetical planar circle. Whether a real sensor covers a location also depends on walls, interference, mounting orientation, and measurement units; a circle is a **simplified model**, not a complete physical simulation.

## 27. Key Geometric Operators and Functions to Know

Commonly used operators/functions:

| Operation | Meaning | Example |
|---|---|---|
| `<->` | Distance between objects for supported pairs | `point(0,0) <-> point(3,4)` |
| `@>` | Left operand contains right operand, for supported types | `box(...) @> point(...)` |
| `<@` | Left operand is contained in right operand, for supported types | `point(...) <@ box(...)` |
| `&&` | Two shapes overlap, for supported combinations | `box(...) && box(...)` |
| `area()` | Area for supported shape types | `area(box(...))` |
| `length()` | Length for supported linear types | `length(lseg(...))` |
| `center()` | Center of supported shapes | `center(box(...))` |
| `npoints()` | Number of points in a path/polygon for supported functions | `npoints(path_value)` |

**This does not mean every operator in the table works on every combination of `point`, `circle`, `polygon`, and `line`.** PostgreSQL defines an operator matrix per type pair. When switching from one type to another, verify the exact operator/function signature.

### 27.1. Checking with pg_type and pg_operator When Needed

You can inspect available types and operators on your instance:

~~~sql
SELECT
    typname,
    typtype
FROM pg_catalog.pg_type
WHERE typname IN (
    'inet', 'cidr', 'macaddr', 'macaddr8',
    'bit', 'varbit',
    'point', 'line', 'lseg', 'box',
    'path', 'polygon', 'circle'
)
ORDER BY typname;
~~~

Catalog metadata reveals which types are present. For specialized operations, `psql` also provides client meta-commands to list functions/operators and inspect argument types. Avoid reinventing operations via string parsing when PostgreSQL already provides an appropriate operator.

## 28. Geometric Indexing: GiST and Distance Queries

Geometric queries differ from standard equality lookups:

- Find points near location x.
- Find intersecting boxes.
- Find regions containing a point.
- Find the k nearest objects.

PostgreSQL provides operator classes for specific geometric types on **GiST**, and in some cases **SP-GiST**, depending on the type, operator, and version.

Example GiST index on a `point` column:

~~~sql
CREATE INDEX idx_sensor_position_gist
ON typed_lab.sensor
USING gist (position);
~~~

A nearest-neighbor query:

~~~sql
SELECT
    sensor_id,
    sensor_name,
    position
FROM typed_lab.sensor
ORDER BY position <-> point(5, 5)
LIMIT 2;
~~~

With an operator class supporting nearest-neighbor search, PostgreSQL can use a GiST index for distance ordering in applicable cases.

Verify:

~~~sql
EXPLAIN
SELECT sensor_id, position
FROM typed_lab.sensor
ORDER BY position <-> point(5, 5)
LIMIT 2;
~~~

Because the demo table has only three rows, PostgreSQL may choose a sequential scan and sort instead of the index. That is completely normal: the planner is free to pick the lower-cost strategy based on statistics.

### 28.1. Do Not Assume "One Index Covers Every Query"

GiST supports specific geometric operators, yet:

- Not every operator shares the same operator class.
- Indexes add overhead on INSERT/UPDATE/DELETE.
- Spatial data distribution affects index effectiveness.
- `point`, `box`, and `polygon` have different indexing capabilities.
- Real GIS problems may need PostGIS `geometry`/`geography` with different index features.

Start from actual queries and `EXPLAIN (ANALYZE, BUFFERS)` on representative data rather than merely verifying that `CREATE INDEX` succeeded.

## 29. How Do PostgreSQL Built-in Geometric Types Differ from PostGIS?

This is an important boundary.

**PostgreSQL built-in geometric types:**

- Built right into the core DBMS.
- Support basic planar geometries.
- Fit planar coordinate data, floorplans, and simple 2D technical graphics.
- Do not store geographic reference systems / SRIDs like a dedicated GIS model.
- Operator set is not intended to replace a full GIS engine.

**PostGIS (extension):**

- Adds dedicated spatial types and functions, notably `geometry` and `geography`.
- Models coordinate reference systems / SRIDs and performs rich spatial analysis.
- Supports complex shapes and specialized operations depending on version and features.
- Much better suited for GIS, large spatial datasets, standard coordinate systems, geographic area/distance calculations, and coordinate transforms.

Example you **should not** write:

~~~sql
-- This is only Euclidean distance between two number pairs,
-- not kilometers between two geographic locations.
SELECT point(106.7, 10.8) <-> point(105.8, 21.0);
~~~

Those numbers look like longitude/latitude, yet the result is measured in **planar coordinate degrees**, not meters or kilometers.

When you need true Earth-surface distances, define the SRID, units, and algorithm, and pick an appropriate GIS tool instead of multiplying planar results by a fixed conversion constant.

## 30. Numeric Types and Precision in Geometry

Built-in geometric types operate on floating-point coordinates, which can exhibit representation and rounding inaccuracies.

Example area calculation:

~~~sql
SELECT
    area(circle(point(0, 0), 5)) AS area_value;
~~~

The result is a floating-point approximation of the mathematical value. Never feed such results directly into exact-decimal financial accounting.

When an application checks whether two points are "nearly equal," define an error tolerance in the coordinate system's units:

~~~sql
SELECT
    (point(1.0, 1.0) <-> point(1.000001, 1.0)) < 0.001
        AS near_enough;
~~~

The `0.001` threshold only makes sense once coordinate units are agreed upon. Never apply one hardcoded epsilon across every system and scale.

## 31. Choosing Types by Application Semantics, Not String Appearance

Some commonly confused cases:

| Input Data | Type Usually Considered | Why |
|---|---|---|
| `192.168.1.10` as a request IP | `inet` | Represents an IPv4 host |
| `192.168.1.0/24` as an ACL subnet | `cidr` | Represents a network block |
| `2001:db8::1` as an IPv6 address | `inet` | Same column can hold IPv4 and IPv6 |
| `08:00:2b:01:02:03` as a MAC | `macaddr` | 48-bit hardware address |
| 8-bit protocol flags | `bit(8)` | Fixed length and bit positions |
| Variable-length bitmap up to 128 bits | `bit varying(128)` | Not every row needs 128 bits |
| Location on a factory floorplan | `point` | Planar coordinates |
| Circular sensor coverage on a blueprint | `circle` | Center and radius |
| Rectangular area on a 2D plane | `box` | Axis-aligned bounding box |
| Multi-vertex boundary on a 2D plane | `polygon` | Simple polygonal region |
| GPS location with SRID and meter distances | PostGIS `geometry`/`geography` when suitable | Geographic problem, not pure planar point |
| Byte-oriented binary file data | `bytea` | Byte structure rather than bit string |

Do not use `cidr` for a URL, do not use `macaddr` for an IP address, do not use `bit(8)` to pack human-readable boolean flags that change frequently, and do not use `point` instead of geographic coordinates when the problem requires GIS.

## 32. Queries Combining Network, Bit, and Geometric Data

Suppose you want to find which devices have monitoring enabled and lie near a given location:

~~~sql
SELECT
    device_id,
    asset_name,
    hardware_address,
    feature_flags,
    location_2d,
    location_2d <-> point(0, 0) AS planar_distance
FROM typed_lab.device
WHERE get_bit(feature_flags, 0) = 1
  AND location_2d IS NOT NULL
ORDER BY
    location_2d <-> point(0, 0),
    device_id;
~~~

The SQL above demonstrates three specialized data types in a single device table:

- `hardware_address` is a MAC address, not geographic data.
- `feature_flags` is a bitmask interpreted by application mapping.
- `location_2d` is a planar position used for distance calculation.

If devices are identified by IP rather than MAC, add a dedicated `inet` column and recognize that the device–IP relationship can be **one-to-many or change over time** (e.g., DHCP, multiple interfaces).

### 32.1. Modeling Relationships Between IP, MAC, and Devices

A single device can:

- Hold multiple IPv4/IPv6 addresses.
- Change IP addresses over time.
- Have multiple network interfaces / MACs.
- Use MAC address randomization.
- Connect through proxies/NAT so server logs see a different IP from the physical device.

Therefore, do not collapse everything into a single `device_address TEXT UNIQUE` column.

A stricter model might have `device`, `device_interface`, `assigned_ip`, and `assignment_history` tables with appropriate constraints/time ranges. Use `inet` for IPs and `macaddr`/`macaddr8` for interface identifiers when the semantics truly match.

## 33. Migrating from TEXT to Specialized Types

Suppose a legacy system has:

~~~sql
CREATE TABLE typed_lab.import_ip_text (
    id INTEGER PRIMARY KEY,
    ip_text TEXT NOT NULL
);

INSERT INTO typed_lab.import_ip_text
    (id, ip_text)
VALUES
    (1, '192.168.10.12'),
    (2, '2001:db8::8'),
    (3, 'not-a-real-ip');
~~~

Do not blindly run:

~~~sql
-- Expected to fail due to invalid value:
-- ALTER TABLE typed_lab.import_ip_text
-- ALTER COLUMN ip_text TYPE INET
-- USING ip_text::inet;
~~~

The value `not-a-real-ip` cannot be cast to `inet`. To migrate safely:

1. Define allowed input rules.
2. Profile the data and locate invalid values.
3. Clean data or quarantine invalid rows per business rules.
4. Test the migration on staging.
5. Update code/drivers/ORM mappings if column types change.
6. Execute the conversion with an appropriate locking/downtime plan or phased migration.
7. Verify data and indexes after conversion.

### 33.1. Avoid Uncontrolled Full-Table Type Conversions

An `ALTER COLUMN ... TYPE INET USING ...` on a large table can rewrite many rows, acquire heavy locks, and take a long time. In production, plan a phased migration rather than relying on a single command that worked on a small demo table.

### 33.2. Network Data May Canonicalize on Write

How PostgreSQL formats IPv6 or MAC values on output can normalize their representation. Therefore, if an application relies on the **exact verbatim raw input string** for auditing or digital signatures, store a separate controlled raw string column alongside the normalized typed column.

The typed column serves network comparisons; the raw column (if truly needed) serves traceability, not subnet matching.

## 34. JDBC and Specialized Types

In Java/JDBC, specialized PostgreSQL types may not map directly to a simple standard Java type like `String` or `Integer`.

Points to note:

- The PostgreSQL JDBC driver has its own handling for server-specific types.
- ORM frameworks may require custom mappings or converters.
- `inet`/`cidr` must be parsed/serialized in valid formats.
- `bit`/`varbit` may require length control and explicit Java mapping.
- `point`/`circle` may require driver-specific classes or libraries.
- When sending an untyped `?` parameter, PostgreSQL may require an explicit cast to know the expected type.

SQL example using a typed parameter cast:

~~~sql
SELECT
    event_id,
    remote_ip
FROM typed_lab.access_event
WHERE remote_ip <<= CAST(? AS CIDR);
~~~

In JDBC, `?` is a parameter marker; you can bind a CIDR string compatible with the driver and let PostgreSQL cast it to `cidr`. Never concatenate network input directly into SQL strings.

A simple Java JDBC example checking IP ranges via a text parameter:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public class NetworkQueryDemo {
    public static void main(String[] args) throws Exception {
        String url = System.getenv("POSTGRES_JDBC_URL");
        String user = System.getenv("POSTGRES_USER");
        String password = System.getenv("POSTGRES_PASSWORD");

        String sql = """
            SELECT event_id, remote_ip::text
            FROM typed_lab.access_event
            WHERE remote_ip <<= CAST(? AS CIDR)
            ORDER BY event_id
            """;

        try (Connection con =
                 DriverManager.getConnection(url, user, password);
             PreparedStatement ps = con.prepareStatement(sql)) {

            ps.setString(1, "192.168.10.0/24");

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    System.out.println(
                        rs.getLong(1) + " " + rs.getString(2)
                    );
                }
            }
        }
    }
}
~~~

This example uses **Java text blocks** (Java 15+) and assumes a compatible PostgreSQL JDBC driver is on the classpath. Passwords are never hardcoded in source code. This is an illustrative snippet, not a replacement for production TLS configuration, connection pooling, and full query hardening.

## 35. NULL and Constraints with Specialized Types

A data type only guarantees that **non-NULL** values conform to the type's format; it does not decide whether a column is required.

Example:

~~~sql
CREATE TABLE typed_lab.network_policy (
    policy_id BIGINT PRIMARY KEY,
    network_block CIDR NOT NULL,
    policy_action TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT chk_network_policy_action
        CHECK (policy_action IN ('allow', 'deny'))
);
~~~

Here:

- `CIDR` validates the network range format.
- `NOT NULL` requires a value to be present.
- `CHECK` restricts allowed policy actions.
- `PRIMARY KEY` enforces row identity.

Similarly, with `point`:

~~~sql
-- The position field can be nullable if location is not yet known.
-- If coordinates are mandatory, declare POINT NOT NULL.
~~~

The `point` type **does not automatically block NULL** and does not know whether coordinates lie inside the valid bounds of a blueprint. Add constraints/logic to validate coordinate domains as needed by the application.

## 36. Common Mistakes

### Mistake 1 — Using TEXT for All IPs

The application has to parse strings and implement network containment manually.

**Better approach:** use `inet`/`cidr` when a column truly holds IPs/network blocks, paired with suitable constraints.

### Mistake 2 — Confusing inet and cidr

Storing `192.168.10.15/24` into `cidr` as if it were a canonical network block.

**Better approach:** `inet` for host addresses with optional prefix; `cidr` for network addresses whose host bits match the prefix boundary.

### Mistake 3 — Using << Instead of <<= When the Network Itself Should Match

Two equal subnets do not satisfy strict containment.

**Better approach:** choose between strict (`<<`) and inclusive-or-equal (`<<=`) according to the requirement.

### Mistake 4 — Treating an IP Address as a Permanent Identity

NAT, VPNs, proxies, and DHCP constantly change the mapping between IPs and users/devices.

**Better approach:** store separate business IDs; use IP addresses for time-scoped observation.

### Mistake 5 — Assuming You Can Capture Every Web Client's MAC Address

MAC addresses normally do not traverse routers across the Internet to application servers.

**Better approach:** only use `macaddr`/`macaddr8` when the data source actually provides link-layer interface identifiers.

### Mistake 6 — Using MAC Addresses as Security Credentials

MAC addresses can be spoofed or randomized.

**Better approach:** use proper authentication/authorization mechanisms rather than relying on MAC alone.

### Mistake 7 — Confusing BIT(8) with an 8-Bit Integer

`BIT(8)` is a bit string of length 8; it does not behave like an integer in all expressions.

**Better approach:** decide whether you need a bitmask or integer arithmetic before picking the type.

### Mistake 8 — Inconsistent Bit Ordering

The client numbers bit 0 from the right while PostgreSQL `get_bit` on bit strings counts from the left.

**Better approach:** document bit mapping clearly and test conversions between Java and PostgreSQL.

### Mistake 9 — Lossy Casting to bit(n)

Explicit casting can pad or truncate bits instead of raising an error.

**Better approach:** validate input length before casting whenever bit integrity matters.

### Mistake 10 — Using Bitmasks for Numerous Dynamic Business Flags

An unversioned bitmap quickly becomes unreadable and fragile across updates.

**Better approach:** consider BOOLEAN columns or a relational table keyed by feature code.

### Mistake 11 — Using point to Compute Kilometers from Longitude/Latitude

`<->` returns Euclidean distance in coordinate units, not geographic distance.

**Better approach:** use PostGIS or appropriate GIS tooling for SRID-aware data and geographic measurements.

### Mistake 12 — Treating box as an Arbitrary Polygon

`box` is an axis-aligned rectangle, not an arbitrary polygonal boundary.

**Better approach:** use `polygon` or PostGIS when complex shapes are needed.

### Mistake 13 — Mixing Coordinate Units

One sensor reports meters while another reports pixels, yet both write to the same `point` column.

**Better approach:** standardize units and coordinate axes in the schema, documentation, and application constraints/mappings.

### Mistake 14 — Assuming GiST Is Always Used by the Planner

For small tables, a sequential scan can be cheaper.

**Better approach:** run `EXPLAIN` on representative data/workloads and choose indexes matching the operator class.

### Mistake 15 — Storing Raw Network Strings and Comparing as Text

IPv6 addresses can have multiple equivalent textual forms.

**Better approach:** compare using `inet`/`cidr`; keep raw text only if genuinely required for auditing.

### Mistake 16 — Failing to Audit Data Before Migrating TEXT to INET

A single malformed string aborts the entire migration.

**Better approach:** profile, clean, and test the conversion in staging first.

## 37. Workflow for Choosing Data Types in a New Table

When encountering a new field, follow these steps:

**Step 1 — Identify the true meaning.** Is it a host IP, network range, 48/64-bit hardware address, bitmap, or planar coordinate?

**Step 2 — Identify required operations.** Equality, containment, prefix matching, bitwise flags, nearest-neighbor lookup, or geometric intersection?

**Step 3 — Choose an expressive type.** `inet` for IPs, `cidr` for networks, `macaddr`/`macaddr8` for appropriate hardware IDs, `bit`/`varbit` for bit strings, `point`/`box`/`circle`/`polygon` for planar shapes.

**Step 4 — Add constraints.** `NOT NULL`, `CHECK`, `UNIQUE`, foreign keys, and length/unit conventions.

**Step 5 — Document value domains.** Prefix rules, bit positions, measurement units, coordinate axes, and validity rules.

**Step 6 — Verify client/ORM behavior.** Does the data serialize/deserialize cleanly? Are parameter casts needed?

**Step 7 — Test indexes and workloads.** Inspect `EXPLAIN`, operator classes, selectivity, and write overhead.

**Step 8 — Plan data operations.** Access controls for IP/MAC data, log retention, and migration paths as the application evolves.

The key principle is to **choose types based on operations and data semantics**, not merely because a value looks like a string of characters.

## 38. Practice Exercises

### Exercise 1 — inet or cidr?

Classify four values: user IP `192.168.1.7`, range `192.168.1.0/24`, IPv6 host `2001:db8::7`, and IPv6 ACL block `2001:db8::/32`.

**Hint:** hosts use `inet`; networks use `cidr`.

### Exercise 2 — Host and Network

Write SQL using `host()` and `network()` on `INET '10.20.30.45/24'`. How do the two results differ?

**Hint:** host remains `10.20.30.45`, while the network part is `10.20.30.0/24`.

### Exercise 3 — Strict Containment

Why is `CIDR '10.0.0.0/8' << CIDR '10.0.0.0/8'` false, while using `<<=` is true?

**Hint:** strict containment differs from contained-or-equal.

### Exercise 4 — JOIN with Two Nested Subnets

How many subnets in the example `typed_lab.allowed_network` table match IP `192.168.10.200`?

**Hint:** it matches both Office `/24` and Office management `/25`. A regular JOIN returns two rows.

### Exercise 5 — Longest Prefix Match

Write SQL selecting the single subnet with the longest prefix for each event.

**Hint:** `LEFT JOIN LATERAL` and `ORDER BY masklen(network_block) DESC LIMIT 1`.

### Exercise 6 — MAC Is Not IP

Why should you not use `macaddr` to store HTTP client IP addresses?

**Hint:** MAC belongs to the link layer and is usually absent in requests routed across the Internet; IP and MAC are completely different address types.

### Exercise 7 — Bit String Length

Compare `BIT(8)` and `BIT VARYING(8)` when storing `B'101'`.

**Hint:** fixed-width requires an exact bit count under assignment rules; varying allows shorter lengths.

### Exercise 8 — AND, OR, XOR Results

Evaluate:

~~~sql
SELECT
    B'1100' & B'1010',
    B'1100' | B'1010',
    B'1100' # B'1010';
~~~

**Hint:** results are `1000`, `1110`, and `0110` respectively.

### Exercise 9 — Bit Position

What does `get_bit(B'10101010', 0)` return? Why?

**Hint:** it returns `1`; bit 0 is on the left side of the bit string.

### Exercise 10 — Toggling a Flag

Write an UPDATE to set bit at position 2 in `feature_flags BIT(8)` without altering other bits.

**Hint:** `set_bit(feature_flags, 2, 1)`.

### Exercise 11 — Flag Mapping Bug

Java numbers bits from the right while PostgreSQL uses `get_bit` from the left. What can go wrong?

**Hint:** the two sides enable/read the wrong feature flags, causing business bugs even though the 8-bit string is syntactically valid.

### Exercise 12 — Point Distance

Compute the distance from `point(0,0)` to `point(6,8)` using `<->`.

**Hint:** 10 coordinate units.

### Exercise 13 — Box and Polygon

When is `box` sufficient to represent a region, and when do you need `polygon`?

**Hint:** `box` is for axis-aligned rectangles; `polygon` is for multi-vertex and more complex shapes.

### Exercise 14 — Open/Closed Paths

Identify the two literals:

~~~sql
SELECT
    PATH '[(0,0),(1,1),(2,0)]',
    PATH '((0,0),(1,1),(2,0))';
~~~

**Hint:** square brackets indicate an open path; outer parentheses indicate a closed path.

### Exercise 15 — Circle

Write SQL to test whether `point(3,4)` lies inside a circle centered at (0,0) with radius 6.

**Hint:** `circle(point(0,0),6) @> point(3,4)`.

### Exercise 16 — Distance Units

An application stores longitude/latitude pairs. Why can't you directly use the output of `point(x1,y1) <-> point(x2,y2)` as kilometers?

**Hint:** those coordinates are angular degrees on Earth, whereas the operator returns planar Euclidean distance.

### Exercise 17 — GiST Index

Create a GiST index on `typed_lab.sensor(position)` and run `EXPLAIN` on a query finding the 3 sensors closest to `point(5,5)`. Why might a small table skip the index?

**Hint:** a sequential scan plus sort can be cheaper when row counts are very small.

### Exercise 18 — Migration TEXT → INET

A legacy table contains a row with `not-a-real-ip`. What happens if you alter the whole column to `inet` without cleaning the data first?

**Hint:** conversion fails on the invalid row; data profiling and a controlled migration are needed.

### Exercise 19 — Schema Design

Design a device management table with an ID, one current IP address, one optional MAC, and 16-bit flags.

**Hint:** `BIGINT`/`INTEGER` for ID, `INET` for IP, `MACADDR` for MAC, `BIT(16)` for flags; then evaluate whether IP history tracking is needed.

### Exercise 20 — Choosing Types for GIS

An application wants to find delivery points within 5 km along the Earth's surface from a store using longitude/latitude. Is built-in `point` sufficient?

**Hint:** do not use it directly for kilometer distances; consider PostGIS `geography`/`geometry` with an appropriate coordinate reference system and algorithm.

## 39. Summary

- **`inet`** stores IPv4/IPv6 addresses with an optional prefix while preserving host bits; **`cidr`** represents canonical network blocks aligned to their prefix.
- Operators **`<<`, `<<=`, `>>`, `>>=`, `&&`** test network ranges; they do not mean the same thing as bit-shift operators on bit strings.
- Functions **`host`, `network`, `masklen`, `family`** analyze network addresses without manual string splitting.
- **`macaddr`** represents 48-bit hardware identifiers and **`macaddr8`** represents 64-bit identifiers; neither replaces IPs or authenticates devices.
- **`BIT(n)`** enforces fixed width while **`BIT VARYING(n)`/`VARBIT(n)`** handles variable-length bit strings up to a limit; explicit casts can pad or truncate bits.
- Bitwise operators **AND/OR/XOR/NOT/shift** along with `get_bit` and `set_bit` manipulate bitmaps, provided bit numbering and lengths are consistent.
- Built-in geometric types include **`point`, `line`, `lseg`, `box`, `path`, `polygon`, `circle`**, serving two-dimensional planar calculations.
- Point distance **`<->`** is Euclidean in coordinate units; **not geographic kilometers** when inputs are longitude/latitude.
- PostgreSQL offers **GiST/SP-GiST and B-tree operator classes** for specific type/operator pairs; choose based on workload and verify with `EXPLAIN`.
- Choose types according to **data semantics and required operations**, alongside appropriate constraints, indexes, driver mappings, retention policies, and access controls.
- When a problem requires spatial reference systems, coordinate transformations, geographic distances, or advanced GIS, evaluate **PostGIS** instead of assuming built-in geometric types are enough.

PostgreSQL's specialized types shine when **the meaning of data is encoded directly into the schema**. An `inet` column clearly states "this is an IP address," `cidr` states "this is a network," `bit(8)` states "this is an eight-bit string with defined bit positions," and `point` states "this is a planar coordinate." Choosing the right type and understanding its boundaries makes queries expressive, validates data close to storage, and spares applications from reimplementing logic already built into PostgreSQL.
