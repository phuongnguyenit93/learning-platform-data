# Domain management, TTL, and safe DNS cutover

## 1. Objectives and context

In the **DNS and traffic management** chapter of the Oracle Cloud Infrastructure (OCI) module, DNS changes are part of service operations: moving a website to a new load balancer, replacing a Compute address, migrating DNS hosting to OCI, or preparing to shift traffic across regions.

A successful record edit in the Console does not mean every client already uses the new result. Safe cutovers require managing domain ownership, authoritative data, delegation, caching, application health, and how long the old system is kept running.

After this lesson, you can:

- Categorize changes to identify the right system and accountable owner.
- Document domain profiles, TTLs, and DNS dependencies that must be preserved.
- Calculate preparation windows for lowering TTLs, monitoring cutover, and rollback.
- Migrate endpoints or DNS hosting to OCI in staged phases.
- Verify authoritative servers, delegation, recursive resolvers, and the application.
- Select retirement criteria for old resources based on observations and operational requirements.

The names `example.com`, `lab.example.com` and addresses `203.0.113.x`, `2001:db8:...` in this lesson are illustrative only. During hands-on practice, replace them with names you control and real endpoints. Timelines, TTLs, and acceptance thresholds are examples and must be adjusted per system.

## 2. Distinguishing types of cutovers

Before editing any configuration, clearly state the objective: changing where the domain is registered, changing where DNS is answered, or changing where the application is served.

| Change | Primary component affected | What does not happen automatically |
| --- | --- | --- |
| Change service target IP or hostname | A, AAAA, CNAME, or corresponding endpoint mechanism | Does not automatically change registrar or nameservers |
| Migrate DNS hosting to OCI | Target zone, DNS data, and NS delegation | Does not automatically transfer domain registration |
| Transfer registrar | Account and domain registration management process | Does not force a DNS hosting change |
| Change user-facing domain name | DNS, certificates, application, URLs, and integrations | Not solved by a CNAME alone |
| Move service to another region | Endpoints, data, application configuration, and related DNS | DNS does not replicate databases or storage |

OCI DNS is not a registrar. To point a registered domain's delegation to OCI, administrators must update nameservers through the registrar; for a child zone, update NS records in the corresponding authoritative parent zone. [Oracle: Delegating a Public DNS Zone](https://docs.oracle.com/en-us/iaas/Content/DNS/Concepts/gettingstarted_topic-Delegating_Your_Zone.htm)

For example, moving `api.lab.example.com` from an old load balancer to a new load balancer typically requires only changing the target data. There is no need to change delegation for all of `example.com`.

Conversely, if migrating hosting of `lab.example.com` from another provider to OCI while keeping the same application endpoints, keep the application data identical during the NS transition phase. Separating these changes makes root-cause identification and rollback clearer.

## 3. Managing domains as operational assets

### 3.1. Minimum profile for each domain or zone

| Information | Purpose |
| --- | --- |
| Domain name, parent zone, and child zones | Define administrative and delegation boundaries |
| Registrar, account owner, recovery channels | Ensure the organization can maintain and recover administrative access |
| Expiration date, renewal owner | Avoid outages caused by registration expiry |
| Current DNS provider, nameservers | Know where authoritative answers actually come from |
| OCI compartment, OCID, and zone scope | Avoid editing the wrong resource with a matching name |
| DNSSEC status, where DS is managed | Plan the chain of trust when changing NS |
| Configuration source and authorized editors | Prevent overwrites between Console and pipelines |
| Services and teams using the domain | Assess impact beyond the main website |
| Rollback plan, old-system retention window | Have a prepared recovery path |

The registrar account should be under organizational control with appropriate authentication and recovery mechanisms. Emergency contact channels must have an option that still works even when the domain itself is experiencing an outage.

Use renewal reminders, alerts, and explicit ownership assignments. Enabling auto-renewal does not replace verifying payment methods and domain status. Expiration, redemption, or registrar transfer rules depend on the registrar and TLD; check the applicable process rather than assuming a single universal timeline.

### 3.2. Permissions in OCI vs. permissions at the registrar

Someone authorized to edit RRsets in OCI is not necessarily authorized to change NS or DS at the registrar. The cutover plan must identify who executes each part and who holds rollback authority.

In OCI, separate permissions for reading zones, editing records, and managing zone lifecycles. Access can be scoped by compartment, zone, domain name, or record type. Do not grant full DNS permissions across the tenancy just because a task needs to update one A RRset. [Oracle: Details for the DNS Service](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/dnspolicyreference.htm)

Before the cutover window, confirm permissions via read operations and scope checks. Do not wait until the moment of the NS switch to discover the owner lacks access to the parent zone.

## 4. What does TTL actually control?

### 4.1. TTL binds to cached data

Suppose the current record is:

```text
api.lab.example.com.  3600  IN  A  203.0.113.10
```

A resolver receiving the record at 09:00 can use the cached result for a duration corresponding to the TTL. If the authoritative server changes the IP at 09:10, it does not send a revocation command to all caches holding the old result.

If you simultaneously lower the TTL from 3600 to 300 at 09:10, caches already holding the earlier data are not retroactively shortened to 300 seconds.

Therefore, the preparation process must consist of two separate changes:

1. Lower the TTL while keeping the RDATA unchanged.
2. Wait out the planned old TTL window, and only then change the RDATA.

A low TTL helps new queries refresh data more frequently. It does not guarantee every client on the Internet switches addresses within an exact fixed number of seconds.

### 4.2. There is no single TTL for an entire hostname

A resolution path can traverse multiple pieces of data:

```text
www.lab.example.com.  CNAME  api.lab.example.com.
api.lab.example.com.  A      203.0.113.10
api.lab.example.com.  AAAA   2001:db8:42::10
```

CNAME, A, and AAAA are distinct RRsets with separate cache durations. Lowering the CNAME TTL does not lower the target's A TTL; changing A does not automatically change AAAA.

When migrating DNS hosting, you must also consider NS delegation in the parent zone and NS at the apex. If the zone uses DNSSEC, DS and DNSKEY introduce additional timing dependencies. A 300-second TTL on an A record does not mean NS or DS caches expire in 300 seconds as well.

A preparation table should clearly record:

| Data | Old value | Planned value | Old TTL | Who can edit |
| --- | --- | --- | --- | --- |
| API A record | Old IP | New IP | Read from current config | OCI DNS team |
| API AAAA record | Old IPv6 or none | Appropriate IPv6 plan | Check separately | OCI DNS team |
| Website CNAME | Current target | Keep or change intentionally | Check separately | Zone owner |
| NS delegation | Old NS | Assigned OCI NS | Read from parent zone | Parent zone owner/registrar |
| DS if present | Current digest | Per DNSSEC plan | Check at parent | Parent zone owner/registrar |

Inspect the authoritative configuration to see the published TTL. The TTL seen through a recursive resolver is usually the remaining time on a cached copy, not the original configured value.

### 4.3. Negative caching

If a client queries a non-existent name, the NXDOMAIN result can be cached. If the name exists but lacks the queried type, it may receive NODATA. Adding the record afterward does not automatically clear negative caches.

According to negative caching rules, the duration relates to the lesser of the SOA TTL and the SOA MINIMUM field in the relevant response. This is not the TTL of the A record just created. [RFC 2308: Negative Caching of DNS Queries](https://www.rfc-editor.org/rfc/rfc2308.txt)

Therefore, provision new hostnames before releasing client configurations. Avoid releasing an application pointing to an uncreated name and expecting a later DNS fix to immediately restore all clients.

### 4.4. Application caches and stale data

Beyond DNS resolvers, caches exist in the OS, runtime, browser, or HTTP libraries. Some resolvers implement serve-stale mechanisms to continue returning old data when they cannot refresh from authoritative servers, improving resiliency. Do not treat TTL as an absolute guarantee of when all stale data disappears. [RFC 8767: Serving Stale Data to Improve DNS Resiliency](https://datatracker.ietf.org/doc/html/rfc8767)

In Java, `InetAddress` caches both successful and failed resolution results. Security properties such as `networkaddress.cache.ttl` and `networkaddress.cache.negative.ttl` affect behavior; inspect the actual JDK and runtime configuration. Do not assume JVM TTL always equals the TTL returned by authoritative DNS. [Java: InetAddress Caching](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/InetAddress.html)

Changing DNS also does not migrate an already open TCP connection, WebSocket, or database session to the new IP. A client only uses the new result when it actually re-resolves and opens a new connection.

## 5. Pre-cutover inventory

### 5.1. Inventory all service-supporting data

Do not record only the website's A record. Audit:

- A, AAAA, and CNAME records for frontend and APIs.
- MX and email-related TXT records such as SPF, DKIM, and DMARC.
- TXT records for domain ownership verification or certificate issuance.
- CAA records and policies affecting certificate issuance.
- Wildcards, SRV, or other record types used by the system.
- NS delegation for child zones.
- DS records, signing state, and DNSSEC dependencies.
- Service-managed records or records with steering policy attachments.

OCI has data types and mechanisms such as ALIAS; when changing providers, compare capabilities and semantics. Do not copy a provider-specific feature as a different standard record just because it looks like a hostname. [Oracle: Managing Resource Records](https://docs.oracle.com/en-us/iaas/Content/DNS/Reference/supporteddnsresource.htm)

A list of DNS queries is not a complete inventory. An `ANY` query cannot replace exporting the zone configuration; wildcards also do not reveal every name actively in use.

### 5.2. Inventory non-DNS dependencies

Confirm the new endpoint already has:

| Component | What to check |
| --- | --- |
| TLS | Valid certificate for the hostname users continue accessing |
| Listener and network | Ports, routes, NSGs, OS firewall, and healthy backends |
| Application | Virtual hosts, callback URLs, cookies, CORS, and allowlists match |
| Data | Database and storage have consistent data as required |
| Integrations | Partners, webhooks, and auxiliary systems accept the new endpoint |
| Monitoring | Ability to distinguish old/new targets and business errors |
| Rollback | Old target remains able to serve, including data state |

If moving an OCI application across regions, DNS does not replicate Oracle Database or Object Storage data. Data strategy, write-cutover timing, and rollback capability must be prepared before redirecting clients.

Keeping two frontends alive simultaneously does not mean two database copies can accept independent writes. The transition phase must align with the actual data architecture.

## 6. Scenario A: migrating endpoint, keeping DNS hosting

### 6.1. Example scope

Suppose the public zone is currently managed by OCI:

```text
Before cutover:
api.lab.example.com.  3600  IN  A  203.0.113.10

After cutover:
api.lab.example.com.   300  IN  A  203.0.113.20
```

The new target has the same business functionality and an appropriate certificate. Nameservers do not change. The addresses above are documentation data; replace them with real IPs during the lab.

### 6.2. Sample cutover schedule

| Time | Action | Gate to proceed |
| --- | --- | --- |
| Before cutover day | Inventory, prepare new endpoint and data plan | New service passes independent testing |
| 08:00 Day 1 | Keep old IP, lower TTL from 3600 to 300 | Authoritative server serves the low TTL |
| After at least the old TTL window since confirmation | Authorize planned IP change step | Client caches and dependencies additionally assessed |
| Selected cutover time | Change A to new IP | Request and readback show accurate RRset |
| Transition phase | Keep old target running, monitor both | Errors, latency, and data stay within thresholds |
| After stabilization | Consider raising TTL and retiring old resources | Defined completion criteria met |

Do not treat clicking Save as the start of the waiting window if changes have not been published or the authoritative server is not yet serving the new TTL.

Under standard caching behavior for identified RRsets, the preparation window must at least account for the largest relevant old TTL. This is a planning condition, not proof that every client switched after that exact duration.

### 6.3. Executing the change in OCI

In the Console, open the right public zone by OCID, select the API's RRset, and modify only the TTL during the preparation step. Save, review the staged change, and click Publish Changes.

At the cutover window, edit the RDATA to the desired target set, publish, and read back. In the Console workflow, staged data is not yet data served to queries. [Oracle: Changing DNS Zone Records](https://docs.oracle.com/en-us/iaas/Content/DNS/Tasks/record-edit.htm)

If using the API/CLI, note that updating an RRset replaces the entire set of records at that owner/type. The example below is only for a lab A RRset confirmed to have a single address to replace:

```bash
DNS_ZONE_OCID='REPLACE_WITH_OCI_PUBLIC_ZONE_OCID'

oci dns record rrset update \
  --zone-name-or-id "$DNS_ZONE_OCID" \
  --domain 'api.lab.example.com' \
  --rtype A \
  --scope GLOBAL \
  --items '[
    {"domain":"api.lab.example.com","rtype":"A","ttl":300,"rdata":"203.0.113.20"}
  ]'
```

If the RRset has multiple addresses that must be preserved, the request must include all of those values. For automation with concurrent editors, use a valid version/ETag condition via `--if-match` when appropriate, handling conflicts by re-reading. [Oracle CLI: Update RRset](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/dns/record/rrset/update.html)

Do not assume updating A and AAAA is a single atomic transaction. If both must change, prepare endpoints and sequencing so intermediate states remain acceptable.

## 7. Scenario B: migrating DNS hosting to OCI

This scenario changes where authoritative answers are served. The initial goal is to preserve application behavior while changing DNS hosting.

### 7.1. Preparing the target zone before delegation

1. Obtain a complete inventory from the old provider.
2. Create a primary public zone with the exact name in OCI, in the assigned compartment.
3. Import or recreate application records and child delegations.
4. Resolve differences around ALIAS, wildcards, steering, and managed records.
5. Keep the OCI zone's system SOA and NS records per service design; do not replace them with the old provider's NS.
6. Record the complete list of nameservers OCI assigned to the target zone.
7. Query each new nameserver directly and compare the data.

Two providers may use different SOA serials, NS records, and signing data. The goal is to verify equivalence of served data and the delegation path, not to force every administrative record to match byte-for-byte.

Do not treat creating a zone in OCI as proof that the Internet is already using that zone.

### 7.2. Keeping old and new data consistent

During the NS transition, different resolvers may still query the old provider or already query OCI. Both sides must return equivalent application data.

Intentionally apply one of two approaches:

- Freeze non-essential DNS changes during the migration window.
- If changes are still required, update both sides in a controlled manner and verify synchronization.

Designate a single owner or workflow responsible for coordination. Do not let two independent pipelines modify configurations from two conflicting data sources.

Do not mix old NS and new NS into a single list as a way to split traffic 50/50. Resolvers do not treat NS lists as proportional load balancing; every delegated nameserver must be able to answer accurately.

### 7.3. Updating delegation

For a registered domain like `example.com`, change nameservers via the registrar's process. For a child zone `lab.example.com`, update NS delegation in the parent zone `example.com`.

Use the exact set of nameservers assigned by OCI. Updating NS only at the child zone apex does not replace delegation at the parent.

NS records can be cached for a long time. Oracle notes that propagating awareness of new nameservers through resolvers can take 24–48 hours in some cases; do not treat this range as a fixed deadline for all domains. Plan based on TTL, registrar/parent zone state, and actual observations. [Oracle: Delegating a Public DNS Zone](https://docs.oracle.com/en-us/iaas/Content/DNS/Concepts/gettingstarted_topic-Delegating_Your_Zone.htm)

### 7.4. Retaining the old provider

After changing NS, keep the old zone active throughout the calculated transition window. Canceling the old service immediately can cause resolvers holding cached old delegation to fail lookups even though OCI is completely healthy.

Completion criteria must include verifying delegation, consistency from relevant resolvers, and no remaining known dependencies on the old service. Without comprehensive query logs on the old side, use a well-reasoned retention period and additional checks; do not conclude zero clients remain from a single query on a laptop.

Change application IPs only after DNS hosting migration has stabilized, unless requirements force combining both changes and every intermediate state has been evaluated.

## 8. DNSSEC as a separate planning branch

DNSSEC adds authentication to DNS data using signatures and a chain of trust. It does not encrypt response contents and does not replace TLS.

When a zone uses DNSSEC, DS at the parent must match the child zone's keys. Switching to nameservers with different keys while the old DS remains active can cause validating resolvers to return SERVFAIL.

OCI documentation guides migrating a signed zone to OCI by handling DNSSEC disablement on the old side first, copying the data, and then re-enabling DNSSEC on OCI. Do not interpret disabling as simply clicking stop signing immediately. [Oracle: DNSSEC](https://docs.oracle.com/en-us/iaas/Content/DNS/Concepts/dnssec.htm)

Mandatory principles for that plan:

- Inventory DS at the parent, DNSKEY at the child, and related TTLs.
- If migrating via an unsigned state, remove DS per procedure and wait out the DS TTL window before stopping serving signatures that validators still need.
- For zones with child delegations, account for child DS records and chains of trust beneath them rather than mechanically applying a single-zone procedure.
- On OCI, wait for signing configuration readiness, set the right DS at the parent, and complete key management steps per guidance.
- Confirm using validating resolvers and appropriate tools before concluding.

OCI's DNSSEC disablement procedure specifies removing DS and waiting out related TTLs in sequence before disabling or deleting the zone. For other source providers, consult the source provider's official procedure. [Oracle: Disabling DNSSEC on a Zone](https://docs.oracle.com/en-us/iaas/Content/DNS/Tasks/dnssec-disable.htm)

If security requirements prohibit an unauthenticated gap, design a migration approach with provider support and test it separately. Do not assume zone file export/import transfers all key state and chains of trust.

A basic lab can use a child zone without DNSSEC enabled to learn NS migration. Do not apply that exact sequence directly to a zone that has active DS records.

## 9. Cutover verification command suite

The examples use Bash with `dig` and `curl`. Replace placeholders and documentation addresses with real data. Choose a testing source permitted to query under network policy.

### 9.1. Old and new authoritative servers

```bash
DNS_OLD_NS='REPLACE_WITH_OLD_AUTHORITATIVE_NAMESERVER'
DNS_NEW_NS='REPLACE_WITH_ASSIGNED_OCI_NAMESERVER'

dig @"$DNS_OLD_NS" api.lab.example.com. A +norecurse
dig @"$DNS_NEW_NS" api.lab.example.com. A +norecurse

dig @"$DNS_NEW_NS" api.lab.example.com. AAAA +norecurse
dig @"$DNS_NEW_NS" lab.example.com. SOA +norecurse
dig @"$DNS_NEW_NS" lab.example.com. NS +norecurse
```

Repeat the test against each assigned nameserver when needed. Read the status, Answer section, TTL, and `aa` flag; do not look solely at the IP.

When only changing an endpoint inside OCI, the old and new authoritative servers are the same service, differing in data before and after. You do not need to stand up an old nameserver just to run all examples.

### 9.2. Delegation and recursive resolvers

```bash
dig +trace lab.example.com. NS
dig api.lab.example.com. A
dig api.lab.example.com. AAAA

DNS_RECURSOR='REPLACE_WITH_SELECTED_RECURSIVE_RESOLVER_IP'
dig @"$DNS_RECURSOR" api.lab.example.com. A
```

Querying authoritative servers directly checks the source data. `+trace` inspects delegation; standard queries reflect the resolver configured on the host. Each test answers a different question. [Oracle: Testing DNS Using dig](https://docs.oracle.com/en-us/iaas/Content/DNS/Tasks/testingdnsusingdig.htm)

If the network blocks direct outbound DNS to the Internet, trace may time out even though clients can still use the enterprise resolver. If a private view shares the same name, confirm which namespace you are querying.

With DNSSEC, you can inspect related data:

```bash
dig +trace lab.example.com. DS
dig @"$DNS_NEW_NS" lab.example.com. DNSKEY +dnssec +norecurse
dig @"$DNS_RECURSOR" api.lab.example.com. A +dnssec
```

`+dnssec` requests DNSSEC records in the response; it does not turn `dig` into a full validator for every signature. Not seeing the AD flag also does not automatically prove signatures are invalid; understand the resolver, test channel, and validation policy in use.

### 9.3. Testing the new target before changing DNS

```bash
curl --noproxy '*' \
  --resolve 'api.lab.example.com:443:203.0.113.20' \
  --connect-timeout 5 --max-time 15 \
  https://api.lab.example.com/health
```

This command pins the connection address while keeping the hostname for HTTP Host and TLS SNI. A valid certificate for that hostname is required; do not add `-k` to bypass certificate errors.

After the cutover, test via the real DNS path:

```bash
curl --noproxy '*' --connect-timeout 5 --max-time 15 \
  -w '\nremote=%{remote_ip} status=%{http_code} total=%{time_total}\n' \
  https://api.lab.example.com/health
```

If both A and AAAA exist, test separately with `-4` and `-6` from a host with corresponding connectivity. `--noproxy '*'` is for direct testing; if the system requires going through a proxy, add a test via the actual proxy path.

HTTP 200 at a health endpoint is only one criterion. Add representative business transactions if the change can affect login, data reads/writes, or integrations.

## 10. Proceed criteria, rollback, and retiring the old target

### 10.1. Defining thresholds before the change window

Example proceed criteria:

- Authoritative servers return the full desired RRsets.
- Delegation leads to the right set of nameservers in a hosting migration scenario.
- No unexpected DNSSEC validation errors occur.
- TLS and business endpoints pass tests from selected locations.
- Error rates and latency remain within agreed service thresholds.
- Data strategy supports both the transition period and rollback.

Document specific system-appropriate thresholds, decision-makers, and recovery target states beforehand. Do not wait for an incident to debate what counts as failure.

### 10.2. Rollback is also a cutover

If changing the endpoint causes errors, restore the full old RRset and verify authoritatively. Clients that already cached the new IP may continue reaching the new target, so retain handling or appropriate routing there during the transition window.

If NS was just changed, reverting delegation to the old NS set does not instantly pull every resolver back to the old side. Therefore, both zones must remain operational with consistent data per plan.

Do not repeatedly flip back and forth between two IPs just because tests from different caches do not match yet. Oscillating state complicates diagnostics and creates more cached variants.

If modified data is incompatible with the old system, reverting DNS alone is insufficient to roll back the service. An appropriate data strategy or recovery decision must be in place.

### 10.3. Retiring based on multiple signals

Retire only when all are satisfied:

| Category | Evidence |
| --- | --- |
| DNS | Relevant TTL/delegation windows have elapsed and been verified at appropriate sources |
| Client | Runtime caches, critical clients, and long-lived connections evaluated |
| Traffic | Observed long enough across the service's usage cycle |
| Data | No remaining need for synchronization or rollback to the old target |
| Organization | Service owner approves closing the rollback window |
| Resources | Ordered teardown plan exists for DNS, endpoints, certificates, and dependent configs |

"The TTL has expired" is one input, not the sole proof.

## 11. Commonly misdiagnosed situations

| Symptom | What to check first | How to handle |
| --- | --- | --- |
| TTL lowered yet clients still use old IP | Cache populated before the change | Check old TTL and when authoritative started serving low TTL |
| Some clients succeed, others fail | Different resolvers, IPv4/IPv6, private views, or runtime caches | Segment tests by actual path |
| Authoritative is right but client gets NXDOMAIN | Negative cache or querying wrong namespace | Inspect SOA, resolver, and full owner name |
| Some locations time out after NS change | Stale NS cache while old service was shut down | Restore answering capability on the still-queried side |
| SERVFAIL after nameserver migration | Inconsistent DS/DNSKEY chain or delegation | Check validation and data at parent/child |
| Website works but email breaks | Missing MX/TXT or wrong mail target | Compare all email-dependent records |
| Curl pinning new IP succeeds, hostname fails | DNS, proxy, or stale cache | Compare resolution and actual connection path |
| DNS is right but login sessions fail | Cookies, session store, or app configuration | Investigate application layer and data state |
| JVM keeps connecting to old target | Runtime cache or connection pool holding connections | Check JDK config and connection lifecycle |
| Lost an address after update | Request omitted part of the RRset to preserve | Restore full set, fix update workflow |

Do not assume raising or lowering TTL fixes every issue. TTL cannot fix wrong NS, wrong addresses, invalid signatures, broken endpoints, or certificates missing a hostname.

## 12. Automation, observability, and cost on OCI

### 12.1. Recording evidence for every step

A reviewable workflow should retain:

- Snapshot of current configuration and desired target state.
- List of RRsets and delegations actually affected.
- Old TTL, timestamp when low TTL was confirmed, and cutover timestamp.
- Verification results across authoritative servers, resolvers, and business checks.
- Version or ETag used during updates.
- Operator, proceed/rollback decisions, and completion timestamp.

Use Audit to investigate OCI resource management operations, combined with DNS and application measurements. Management logs are not a complete list of every client that received a DNS answer.

### 12.2. Staged automation

Pipelines should split into preparing endpoints, lowering TTL, waiting for conditions, switching RDATA or NS, verifying, and completing. Wait steps should tie to collected TTL data and verification results, not a fixed sleep applied to every zone.

Review infrastructure-as-code plans before applying. A record change should not unintentionally recreate a zone, delete child NS records, or replace an entire dataset owned by another pipeline.

If using Traffic Management or health checks, confirm the answering mechanism and record owner before editing manually. Low TTL does not create failover by itself; multiple IPs in an A RRset also do not automatically remove unhealthy backends.

### 12.3. Balancing cutover speed with cost

Low TTLs can increase authoritative queries depending on client volume and cache behavior. Running two load balancers, Compute instances, or two DNS hosting providers in parallel also incurs cost during the transition window.

Budget for the parallel run window, probe frequency, and log retention. Do not shorten the old-system retention period just to eliminate a minor cost without weighing it against recovery requirements.

Once stabilized, raise TTLs according to operational needs and retire resources following the dependency checklist. Delete records pointing to decommissioned resources before their targets can be claimed by others, while respecting cache windows and transition plans.

## 13. Controlled hands-on lab

Use a clearly delegated lab child zone to avoid impacting the main domain.

1. Prepare two test endpoints returning distinct identifying responses, such as `old` and `new`, both supporting the lab hostname.
2. Publish A pointing to the old target and record the TTL, authoritative, resolver, and application results.
3. Lower the TTL while keeping the old address; confirm publication and observe TTL across layers.
4. Wait out the preparation window based on recorded data.
5. Test the new target using `curl --resolve`, confirming TLS and response content.
6. Switch A to the new target, monitoring both endpoints and resolution results.
7. Rehearse restoring the old RRset; observe why clients do not all switch at the same instant.
8. Document sufficient criteria to retire the unused target and how caches/long-lived connections are handled.

If you want to practice hosting migration, run a follow-up drill within the same lab scope: keep application data equivalent between old DNS and OCI, verify each nameserver, then update NS at the parent. For zones with DNSSEC, add a dedicated plan before taking action.

A satisfactory lab should explain why stale data still appears, prove the new endpoint works before the switch, and specify how to roll back in both DNS and the application. The goal is controlling the transition phase, rather than merely completing a value edit in the Console.