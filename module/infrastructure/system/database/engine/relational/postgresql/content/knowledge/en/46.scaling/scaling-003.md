# pgcrypto and Choosing the Right Cryptographic Function in PostgreSQL

PostgreSQL provides the **pgcrypto** extension to perform several cryptographic operations directly inside the database. The extension includes different groups of functions: hash functions for generating fingerprints, HMAC for authenticating data with a secret key, password hashing functions with salt and adaptive cost, a cryptographic random byte generator, and symmetric and public-key OpenPGP encryption functions.

The most important rule is choosing the right primitive for the right goal. A hash cannot be decrypted; HMAC does not encrypt data; encryption does not replace password hashing; and random tokens should not be generated with an ordinary random function. A wrong choice can expose passwords, allow data tampering without detection, or place the secret key right next to the ciphertext in the same database.

pgcrypto also has trust boundary limitations: its functions execute inside the PostgreSQL server. When an application passes plaintext and a key into a pgcrypto function, the server processes both. A database administrator or anyone who controls the server may be able to observe that data. If the requirement is that even a DBA must not read plaintext, consider client-side encryption before data reaches the database.

This lesson helps distinguish each function group, choose appropriate algorithms and storage formats, manage keys, verify results, and avoid dangerous usage patterns.

~~~text
                  Data Protection Needs
                            |
        +-------------------+-------------------+
        |                   |                   |
        v                   v                   v
  Verify fingerprint   Authenticate data   Protect confidentiality
        |                   |                   |
        v                   v                   v
     digest()             hmac()          pgp_*_encrypt()
                                                |
        +-------------------+-------------------+
        |                   |
        v                   v
   Store password       Random token
        |                   |
        v                   v
  crypt() + gen_salt() gen_random_bytes()

Each branch solves a different problem.
~~~

This lesson belongs to the **Database Engine Relational PostgreSQL** module, **Scaling** chapter, on the topic **“pgcrypto and Choosing the Right Cryptographic Function”**. The content focuses on installing the extension, distinguishing digest/HMAC/password hash/encryption/randomness, using OpenPGP, designing schemas, managing and rotating keys, testing, and operating safely.

---

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain what pgcrypto is and why it is provided as an extension.
2. Install and verify pgcrypto in each database.
3. Distinguish hash functions, HMAC, password hashing, and encryption.
4. Use `digest` to generate SHA-256 or SHA-512 hashes.
5. Understand why a hash cannot authenticate data if an attacker can replace both the data and the hash.
6. Use `hmac` with a secret key to verify integrity and authenticity.
7. Use `crypt` and `gen_salt` to store password hashes with salt and cost.
8. Distinguish bcrypt from legacy password hashing schemes in `crypt`.
9. Know the 72-byte limit of bcrypt and how to handle long passwords.
10. Generate random bytes using `gen_random_bytes` instead of `random()`.
11. Encrypt and decrypt data using `pgp_sym_encrypt`/`pgp_sym_decrypt`.
12. Encrypt with a public key and decrypt with a private key.
13. Use `armor`/`dearmor` and read OpenPGP metadata.
14. Distinguish text functions from bytea functions.
15. Select the right primitive based on requirements: checksum, password, token, integrity, or confidentiality.
16. Design schemas to store ciphertext, key version, and metadata.
17. Manage keys outside the database using a secret manager/KMS/HSM.
18. Understand why server-side pgcrypto does not hide plaintext from the database server.
19. Plan key rotation and ciphertext migration.
20. Evaluate the index and search implications of encryption.
21. Restrict access permissions, logging, and query visibility.
22. Test performance, error handling, and compatibility.
23. Practice digest, HMAC, password hashing, symmetric encryption, and public-key encryption.
24. Build a checklist for operating pgcrypto safely.

**Scope:** Modern PostgreSQL with pgcrypto built/packaged with OpenSSL support. Available algorithm names, extension packages, and certain details may depend on OpenSSL, PostgreSQL version, OS, and service provider. Examples use bind parameter placeholders such as `$1`, `$2`; never put real keys or passwords directly into SQL source.

---

## 2. Cryptographic Fundamentals Before Using pgcrypto

You cannot choose the right function without first defining the security goal.

### 2.1. Confidentiality

Only parties with the appropriate key can read the content. This is the goal of encryption.

For example: encrypting bank account numbers or sensitive notes before storing them.

### 2.2. Integrity

Detecting whether data has changed unintentionally or been modified without authorization. A hash can create a fingerprint, but to defend against an attacker who can recompute the hash, a secret key or signature mechanism is required.

### 2.3. Authenticity

Determining whether data was created by a party holding a valid credential/key. HMAC uses a shared secret; a digital signature uses a private/public key pair.

### 2.4. Password Verification

The system needs to verify that a user knows a password without storing the original password. The appropriate method is password hashing with salt and adaptive cost, not reversible encryption.

### 2.5. Randomness

Tokens, nonces, salts, and keys must be generated from a cryptographic random source. Ordinary random functions intended for simulation or statistics are not suitable for security tokens.

### 2.6. Non-Interchangeable Concepts

| Primitive | Can recover original data? | Uses a secret key? | Primary goal |
| --- | --- | --- | --- |
| digest/hash | No | No | Fingerprint/checksum |
| HMAC | No | Yes | Integrity/authenticity with a shared secret |
| Password hash | No | Uses salt; usually does not need a separate secret | Password verification |
| Symmetric encryption | Yes, with the same key | Yes | Confidentiality |
| Public-key encryption | Yes, with the private key | Public/private key pair | Confidentiality and key distribution |
| Digital signature | Does not recover plaintext from the signature | Private key to sign | Signer authentication and integrity |
| Random bytes | Not a data transformation | Internal CSPRNG | Token, nonce, key material |

pgcrypto provides functions for many rows in this table, but it is not an all-in-one library covering every key management system or digital signature workflow.

---

## 3. Threat Model: Defining Who Must Be Denied Access

Before choosing pgcrypto, define who the data needs to be protected from.

### 3.1. Application Users Who Must Not Read Each Other's Data

You may need to combine:
- PostgreSQL roles and grants.
- Row-level security.
- Application authorization.
- Encryption for certain fields if an additional protection layer is required.

Encryption does not replace authorization.

### 3.2. Backup or Storage Snapshot Theft

Encryption at the database/application layer or storage encryption-at-rest can reduce risk if a backup or snapshot is stolen. Keys must be stored separately from the ciphertext.

### 3.3. Network Eavesdroppers

TLS protects data in transit. pgcrypto itself does not replace TLS between client and server.

### 3.4. Database Administrators or Server Operators

With server-side pgcrypto, plaintext and keys are passed into PostgreSQL for the functions to process. Anyone with sufficient privileges or host control may be able to observe them.

If DBAs must not be able to read plaintext, use client-side encryption with keys available only to the client/trusted service, or an appropriate HSM/KMS architecture.

### 3.5. Attackers Able to Modify Data

An unkeyed hash can be recomputed after modifying the payload. HMAC or a digital signature can detect tampering if the key/private key is protected.

### 3.6. Insiders with Log Access

Query text, error details, audit logs, and tracing can accidentally contain passwords, plaintext, or keys. Do not put secrets in SQL literals and do not write secrets to logs.

### 3.7. No Single Function Addresses Every Threat

A system typically needs multiple layers: TLS, authorization, backup encryption, key management, password hashing, auditing, and database encryption for appropriate fields.

---

## 4. Installing pgcrypto

pgcrypto is an extension, so the package must be present on the server and the extension must be created in each database where it is used.

### 4.1. Check the PostgreSQL Version

~~~sql
SELECT version();
SHOW server_version;
SHOW server_version_num;
~~~

### 4.2. Check Extension Package Availability

~~~sql
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_catalog.pg_available_extensions
WHERE name = 'pgcrypto';
~~~

If no row is returned, the server installation or service may not provide the pgcrypto package. Install the package matching the PostgreSQL major version or check with your managed service provider.

### 4.3. Install the Extension

~~~sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
~~~

This command must be run inside the database that needs to use pgcrypto.

### 4.4. Verify Version and Schema

~~~sql
SELECT
    e.extname,
    e.extversion,
    n.nspname AS extension_schema,
    e.extowner::regrole AS extension_owner
FROM pg_catalog.pg_extension AS e
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = e.extnamespace
WHERE e.extname = 'pgcrypto';
~~~

### 4.5. Per-Database Extension

`CREATE EXTENSION` only installs the extension in the current database. If an application uses multiple databases, check each database individually.

### 4.6. OpenSSL Dependency

pgcrypto relies on OpenSSL for cryptographic operations. If a PostgreSQL build does not include OpenSSL support or the extension package is not provided, you cannot assume `CREATE EXTENSION` will work.

On the host, you can inspect the build configuration with:

~~~bash
pg_config --configure
pg_config --version
~~~

### 4.7. Schema and search_path

Functions are created in the extension's schema. Do not assume they are always in `public` if the extension was installed into another schema.

Use schema-qualified names in security-sensitive code, such as `public.digest(...)` if the extension actually resides in `public`. If the extension is in another schema, substitute the schema name from the catalog.

### 4.8. Installation and Usage Privileges

pgcrypto is marked trusted in PostgreSQL distributions that support this metadata; a user with `CREATE` privilege on the database may be allowed to install it. Managed service or packaging policies may impose additional restrictions. Function invocation privileges remain subject to grants and schema privileges.

### 4.9. Verify Functions After Installation

~~~sql
SELECT
    n.nspname AS function_schema,
    p.proname,
    pg_catalog.pg_get_function_identity_arguments(p.oid) AS arguments,
    pg_catalog.pg_get_function_result(p.oid) AS result_type
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE p.proname IN (
    'digest',
    'hmac',
    'crypt',
    'gen_salt',
    'gen_random_bytes',
    'pgp_sym_encrypt',
    'pgp_sym_decrypt'
)
ORDER BY n.nspname, p.proname;
~~~

---

## 5. digest: Hashing Data

`digest` generates a hash/fingerprint from data. The result is `bytea`; `encode` can be used to display it as hex or base64.

### 5.1. Syntax

**digest(data, type) RETURNS bytea**

`data` can be `text` or `bytea`. `type` is the digest algorithm name.

### 5.2. SHA-256 Example

~~~sql
SELECT encode(
    public.digest('hello PostgreSQL', 'sha256'),
    'hex'
) AS sha256_hex;
~~~

If the extension is not in `public`, replace the schema with the actual schema.

### 5.3. SHA-512 Example

~~~sql
SELECT encode(
    public.digest('hello PostgreSQL', 'sha512'),
    'hex'
) AS sha512_hex;
~~~

SHA-512 produces a longer digest than SHA-256. Choose the algorithm based on interoperability, policy, and use case; a longer digest is not always necessary.

### 5.4. Hashing bytea

~~~sql
SELECT encode(
    public.digest(convert_to('PostgreSQL UTF-8 (café)', 'UTF8'), 'sha256'),
    'hex'
);
~~~

`convert_to` converts `text` to `bytea` using the specified encoding. When multiple systems compute hashes together, they must agree on the encoding and canonical representation.

### 5.5. Common Algorithms

| Algorithm | Notes |
| --- | --- |
| md5 | Legacy; do not use for security-sensitive integrity |
| sha1 | Legacy; collision resistance is no longer suitable for new designs |
| sha224 | SHA-2 with a 224-bit digest |
| sha256 | Common choice for unkeyed fingerprints/integrity |
| sha384 | SHA-2 with a 384-bit digest |
| sha512 | SHA-2 with a 512-bit digest |

Algorithm support may depend on the OpenSSL build. Do not rely on an algorithm being present in a development environment to conclude it exists on every target.

### 5.6. A Hash Is Not Encryption

You cannot decrypt a digest to recover the original plaintext. If the application needs to read the value back, `digest` is not appropriate.

### 5.7. A Hash Does Not Authenticate Origin by Itself

If an attacker can modify both the payload and the digest, they can compute a new digest. To authenticate data with a shared secret, use HMAC; to verify public-key identity, use a digital signature from an appropriate system.

### 5.8. Do Not Use digest to Store Passwords

Passwords typically have low entropy and are easy to guess offline. SHA-256 is very fast, allowing an attacker to try huge numbers of password guesses. Use password hashing with salt and cost such as bcrypt or Argon2id according to policy.

### 5.9. Canonicalization Before Hashing

The same logical data can have multiple byte representations:
- Unicode composed/decomposed forms.
- JSON key ordering/whitespace.
- Timestamp timezone/format.
- Numeric scale/locale.
- Line endings.
- Text encoding.

If multiple systems need to compare digests, normalize the data before hashing and document the canonical format/version explicitly.

### 5.10. File or Payload Fingerprinting

`digest` can be useful for:
- Comparing artifacts.
- Detecting accidental changes when the digest itself is protected.
- Content identification.
- Verifying data after transfer.

For high-security content, an unkeyed digest is insufficient against an active attacker who can replace content.

---

## 6. encode and decode for bytea Results

`digest` and `hmac` return `bytea`. To display or transmit them over text interfaces, use `encode`/`decode`.

### 6.1. Hex

~~~sql
SELECT encode(
    public.digest('sample', 'sha256'),
    'hex'
);
~~~

Hex is human-readable and twice as long as the byte count.

### 6.2. Base64

~~~sql
SELECT encode(
    public.digest('sample', 'sha256'),
    'base64'
);
~~~

Base64 is more compact than hex but contains special characters and may require URL-safe transformation when placed in URLs.

### 6.3. Decode Hex

~~~sql
SELECT decode('48656c6c6f', 'hex');
~~~

`decode` returns `bytea`. The input must have valid encoding.

### 6.4. Do Not Confuse text with bytea

A digest is binary bytes. If stored in a `text` column, encode it explicitly. If stored in `bytea`, there is no need to convert to hex unless a text representation is required.

### 6.5. Binary Equality

`bytea` comparisons can be used for equality logic in the database. However, for MAC verification in contexts where an attacker can observe timing, use constant-time comparison in a trusted application/library rather than assuming every SQL comparison is constant-time.

---

## 7. hmac: Keyed Hashing

HMAC (Hash-based Message Authentication Code) combines a hash algorithm with a secret key. It produces an authentication tag to verify whether a payload has been altered and whether it was created by a party that knows the secret.

### 7.1. Syntax

**hmac(data, key, type) RETURNS bytea**

- `data`: payload as `text` or `bytea`.
- `key`: secret key as `bytea`.
- `type`: digest algorithm.

### 7.2. Example

~~~sql
SELECT encode(
    public.hmac(
        convert_to('order=42&amount=100', 'UTF8'),
        $1::bytea,
        'sha256'
    ),
    'hex'
);
~~~

`$1` is a bind parameter supplied by the client. Do not replace it with a secret literal in SQL source.

### 7.3. Verifying a MAC

The sender and receiver compute the HMAC over the same payload, with the same key and the same algorithm. If the results match, the data can be authenticated within the security scope of the shared key.

### 7.4. HMAC Does Not Encrypt

The payload remains readable. HMAC provides only integrity/authenticity with a secret; confidentiality requires separate encryption.

### 7.5. HMAC vs. digest

| Characteristic | digest | hmac |
| --- | --- | --- |
| Secret key | No | Yes |
| Prevents attacker from recomputing after modifying payload | No, if the digest is unprotected | Yes, if the key is secure |
| Recovers plaintext | No | No |
| Purpose | Fingerprint/checksum | Message authentication |

### 7.6. Choosing a Key

An HMAC key should be generated randomly with sufficient entropy. Do not use a user password directly as an HMAC key. If you need to derive a key from a password, use a KDF designed for that purpose at the appropriate layer.

### 7.7. Agree on Payload Representation

If two parties compute HMAC over JSON, they must agree on canonical JSON, encoding, field ordering, numeric representation, and message format version.

### 7.8. Domain Separation

If the same secret serves multiple purposes, include context/purpose in the MACed data or use separate keys for each purpose. This reduces the risk that a valid MAC in one context is reused in another context.

### 7.9. Replay Protection

HMAC does not prevent replay on its own. If an old message with a valid MAC is re-sent, the MAC remains valid. Add a timestamp, nonce, or sequence number and store used state to control replay.

### 7.10. Comparing MACs

Do not leak details about which byte of a MAC failed. In applications where an attacker can observe timing, verify MACs using constant-time comparison in a trusted application library.

---

## 8. crypt and gen_salt: Password Hashing

Password hashing transforms a password into a one-way verification string. On login, the system recomputes the hash from the entered password and the salt/cost stored inside the previously generated hash.

### 8.1. Syntax

**crypt(password, salt) RETURNS text**

**gen_salt(type [, iter_count]) RETURNS text**

`crypt` is the password hashing function across schemes supported by pgcrypto. `gen_salt` generates a salt formatted appropriately for the chosen scheme.

### 8.2. Bcrypt

For new systems using pgcrypto, bcrypt (`bf`) is usually the most suitable choice among the schemes provided by `crypt`, provided it meets application policy.

~~~sql
SELECT public.crypt(
    $1,
    public.gen_salt('bf', 12)
);
~~~

Here `12` is bcrypt's cost parameter, not a linear iteration count. A higher cost increases computation time exponentially.

### 8.3. Storing Password Hashes

~~~sql
CREATE TABLE app_user_auth (
    user_id BIGINT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    password_scheme TEXT NOT NULL DEFAULT 'pgcrypto-bf',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

~~~sql
INSERT INTO app_user_auth (
    user_id,
    username,
    password_hash
)
VALUES (
    $1,
    $2,
    public.crypt($3, public.gen_salt('bf', 12))
);
~~~

Store only the hash. Never store original passwords, reversible ciphertext, or password logs.

### 8.4. Verifying Passwords

~~~sql
SELECT
    password_hash = public.crypt($1, password_hash) AS password_ok
FROM app_user_auth
WHERE username = $2;
~~~

`crypt` uses the stored hash as the salt/setting to compute a new result. If the results match, the password is verified.

### 8.5. No Separate Salt Column Needed When the Hash Includes the Salt

The bcrypt format stores the scheme, cost, and salt inside the hash string. You do not need an extra salt column for this pattern unless the system has a special design requirement.

### 8.6. Cost Must Be Benchmarked

Cost 12 is only an example. Measure verification time on production-like hardware, realistic concurrency, and your latency budget. Too low a cost weakens brute-force resistance; too high a cost can cause CPU exhaustion during login bursts.

### 8.7. The 72-Byte Limit of Bcrypt

Bcrypt processes at most 72 bytes of password input. With UTF-8, 72 bytes does not necessarily equal 72 characters. If a password is longer, the trailing bytes may be ignored according to bcrypt behavior.

Do not casually prepend `SHA-256(password)` into bcrypt as a quick fix without proper standardization, domain separation, and migration design. When policy requires long passwords or a more modern algorithm, consider Argon2id at the application layer or an organization-approved solution.

### 8.8. Legacy Schemes

pgcrypto `crypt` may support schemes such as DES, extended DES, MD5, and bcrypt depending on build/version. DES, xdes, and md5 are legacy choices; do not use them for new systems when bcrypt or a modern password hashing library is available.

### 8.9. Bcrypt Is Not Encryption

You cannot decrypt a hash to retrieve the password. There is no `crypt_decrypt` function. If data must be recovered, that is an encryption problem, not password storage.

### 8.10. Do Not Reveal Whether a Username Exists

A login endpoint should return a generic message for both nonexistent users and wrong passwords. Avoid letting timing or response codes distinguish whether an account exists, and rate-limit login attempts.

### 8.11. Rehash When Policy Changes

When the cost or scheme needs to increase:
1. Verify the password successfully.
2. Inspect the scheme/cost of the current hash.
3. If it is lower than policy, compute a new hash with the new cost.
4. Update `password_hash` inside a transaction.
5. Record scheme/version metadata if required by the system.

You do not have to reset all passwords immediately if you can safely rehash when users log in.

### 8.12. Argon2id and Modern Policy

pgcrypto `crypt` does not provide Argon2id. If policy requires Argon2id or scrypt, use a maintained password hashing library at the application layer or a solution approved by your security team. Do not substitute `digest(password, 'sha256')`.

---

## 9. gen_random_bytes: Generating Cryptographic Random Data

Tokens, nonces, and key material require a cryptographic random source (CSPRNG).

### 9.1. Syntax

**gen_random_bytes(count) RETURNS bytea**

The function returns the requested number of random bytes. pgcrypto limits a single call to at most 1024 bytes.

### 9.2. Generating a 32-Byte Token

~~~sql
SELECT encode(public.gen_random_bytes(32), 'hex') AS token;
~~~

32 bytes provide 256 bits of raw entropy if the random source is functioning properly.

### 9.3. Generating Secret Key Material

~~~sql
SELECT public.gen_random_bytes(32);
~~~

The `bytea` output can be transferred to a key management system via a secure workflow. Do not store raw keys in the same table as ciphertext.

### 9.4. Do Not Use random()

~~~sql
SELECT random();
~~~

`random()` is meant for general-purpose random numbers, not secure token or key generation.

### 9.5. Salt and Nonce

`gen_salt` creates salts tailored to password hashing schemes; `gen_random_bytes` generates general-purpose random bytes. Do not confuse a bcrypt salt with an encryption key.

### 9.6. Tokens Need Encoding

When placing a token in a text field or URL, encode the bytes with hex/base64 and handle URL-safe encoding at the application layer. Note that standard base64 can contain characters that require escaping.

### 9.7. Randomness Failures

If the system lacks a sufficiently secure random source, the function may raise an error. Do not switch to `random()` to bypass the error; fix entropy/OS/container environment configuration.

---

## 10. Symmetric Encryption with OpenPGP

Symmetric encryption uses the same passphrase/key to encrypt and decrypt.

### 10.1. Core Functions

| Function | Input/output |
| --- | --- |
| pgp_sym_encrypt(text, psw [, options]) | Encrypts text into bytea |
| pgp_sym_decrypt(bytea, psw [, options]) | Decrypts bytea into text |
| pgp_sym_encrypt_bytea(bytea, psw [, options]) | Encrypts binary bytea |
| pgp_sym_decrypt_bytea(bytea, psw [, options]) | Decrypts back to bytea |

### 10.2. Encrypting Text

~~~sql
SELECT public.pgp_sym_encrypt(
    $1::text,
    $2::text
);
~~~

`$1` is plaintext; `$2` is the passphrase bound from a secret management flow.

### 10.3. Decrypting Text

~~~sql
SELECT public.pgp_sym_decrypt(
    encrypted_value,
    $1::text
)
FROM app.customer_secret
WHERE secret_id = $2;
~~~

### 10.4. Storing Ciphertext

~~~sql
CREATE TABLE app.customer_secret (
    secret_id BIGINT PRIMARY KEY,
    ciphertext BYTEA NOT NULL,
    key_version SMALLINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

`key_version` is metadata referencing a key in the key management system. Do not store the passphrase in this table.

### 10.5. Encrypting Binary Data

For non-text payloads such as file fragments or binary blobs, use `pgp_sym_encrypt_bytea` and `pgp_sym_decrypt_bytea`. Do not force `bytea` into `text` via an unsuitable encoding.

### 10.6. OpenPGP Packet Format

pgcrypto uses the OpenPGP format for its PGP functions. Cipher, compression, and string-to-key (S2K) behavior can be tuned via options. Choose options based on interoperability and policy, and do not weaken cipher or integrity protection for speed.

### 10.7. Cipher Option

You can specify a cipher supported by the pgcrypto/OpenPGP build, such as AES-256 when supported on the target:

~~~sql
SELECT public.pgp_sym_encrypt(
    $1::text,
    $2::text,
    'cipher-algo=aes256'
);
~~~

Confirm that the cipher is supported on both source and target and complies with organizational policy. Do not assume every build has the same list of algorithms.

### 10.8. S2K and Passphrase Derivation

OpenPGP uses String-to-Key to derive an encryption key from a passphrase. pgcrypto has options for S2K mode, count, digest, and cipher. This is an OpenPGP-specific mechanism, not a general-purpose KDF API for arbitrary application secrets.

### 10.9. Integrity Protection

OpenPGP encrypted data includes integrity checking according to its format/options. Do not enable options that disable MDC/integrity checks such as `disable-mdc=1` for new data. An integrity packet does not prove the sender's identity; authenticating the sender requires HMAC or an appropriate digital signature.

### 10.10. Passphrases Must Be Strong

A weak passphrase can be brute-forced offline if an attacker obtains the ciphertext. Use a long random secret generated and managed by a KMS/secret manager, or a high-entropy passphrase compliant with policy. Never use an ordinary login password as an encryption passphrase.

### 10.11. Encryption Output Is Non-Deterministic

The same plaintext and passphrase can produce different ciphertexts due to salt/session key/randomness. Never use ciphertext equality as a test for plaintext equality.

---

## 11. Public-Key Encryption

Public-key encryption uses a public key to encrypt and a private key to decrypt.

### 11.1. Core Functions

| Function | Role |
| --- | --- |
| pgp_pub_encrypt(text, public_key [, options]) | Encrypts text with a public key |
| pgp_pub_decrypt(bytea, private_key [, psw [, options]]) | Decrypts with a private key |
| pgp_pub_encrypt_bytea(bytea, public_key [, options]) | Encrypts binary data |
| pgp_pub_decrypt_bytea(bytea, private_key [, psw [, options]]) | Decrypts binary data |
| pgp_key_id(bytea) | Extracts the key ID from a compatible PGP key/message |

### 11.2. Public Key / Private Key

The public key can be distributed to senders. The private key must be kept secret and accessed only by authorized users/services permitted to decrypt.

### 11.3. Encrypting with a Public Key

If the public key is in ASCII-armored text format, use `dearmor` to convert it to `bytea`:

~~~sql
SELECT public.pgp_pub_encrypt(
    $1::text,
    public.dearmor($2::text)
);
~~~

`$2` is the armored public key retrieved from a trusted key registry.

### 11.4. Decrypting with a Private Key

~~~sql
SELECT public.pgp_pub_decrypt(
    encrypted_value,
    public.dearmor($1::text),
    $2::text
)
FROM app.encrypted_message
WHERE message_id = $3;
~~~

The third argument is the private key's passphrase if the private key is passphrase-protected; use the exact signature supported by the installed version.

### 11.5. Public-Key Encryption Is Not a Digital Signature

Anyone who has the public key can encrypt for the recipient. That does not prove who created the plaintext. To authenticate the sender, you need a digital signature using a private signing key and verification with the public key via appropriate tooling/libraries.

### 11.6. Key Generation

pgcrypto provides functions to use PGP keys, not a full key-pair lifecycle management tool. Generate key pairs, back up private keys, revoke, rotate, and publish public keys using approved key management/OpenPGP tooling.

### 11.7. Key ID

`pgp_key_id` can help identify which key was used in a PGP packet. A key ID is not complete proof of trust; use the full fingerprint from key management tooling to verify identity.

### 11.8. Do Not Store the Private Key Next to Ciphertext

If the same database contains both ciphertext and an unprotected private key, an attacker who steals the database gets both. Private keys must be managed outside the database with separate access control and auditing.

---

## 12. armor, dearmor, and PGP Headers

OpenPGP commonly uses either binary representation or ASCII-armored representation.

### 12.1. armor

`armor` converts binary `bytea` into ASCII-armored text:

~~~sql
SELECT public.armor(encrypted_value);
~~~

### 12.2. dearmor

`dearmor` converts ASCII-armored text back to `bytea`:

~~~sql
SELECT public.dearmor($1::text);
~~~

### 12.3. pgp_armor_headers

This function reads armor headers:

~~~sql
SELECT *
FROM public.pgp_armor_headers($1::text);
~~~

The result returns key/value fields according to the armor format.

### 12.4. Headers Are Not Trust Anchors

Do not trust an identity solely because an armor header lists a name or email. Metadata can be forged or unverified by cryptographic identity.

### 12.5. Which Format to Store?

- `bytea` is suitable for storing binary ciphertext in the database.
- `armor` text is convenient for transport across text/email systems.
- Encoding does not make data more secure; security comes from the keys and cryptographic operations.

---

## 13. Which Function to Choose for Each Problem?

| Need | Choice | Avoid |
| --- | --- | --- |
| Fingerprint of a public payload | `digest` with SHA-256/512 | `crypt` or encryption |
| Authenticate payload with a shared secret | `hmac` with SHA-256/512 | Unkeyed `digest` |
| Store user passwords | `crypt` + `gen_salt('bf', cost)`, or Argon2id in app | `digest(password, 'sha256')` |
| Generate token/nonce/key bytes | `gen_random_bytes` | `random()` |
| Encrypt small text field with shared secret | `pgp_sym_encrypt`/`decrypt` | `digest` |
| Encrypt small binary with shared secret | `pgp_sym_encrypt_bytea`/`decrypt_bytea` | Coercing binary to text arbitrarily |
| Encrypt for a specific recipient | `pgp_pub_encrypt`/`decrypt` | HMAC |
| Authenticate a signer | Digital signature tooling | Plain public-key encryption |
| Protect data from DBAs | Client-side encryption/KMS architecture | Server-side pgcrypto alone |
| Equality search on ciphertext | Carefully designed blind index/HMAC token | Comparing randomized ciphertexts |

### 13.1. Questions for Selecting a Primitive

1. Do you need to read the plaintext back? If not, consider hash/password hash.
2. Do you need authentication with a shared secret? Use HMAC.
3. Do you need password verification? Use an adaptive password hash.
4. Do you need unpredictable tokens? Use a CSPRNG.
5. Do you need confidentiality? Use encryption.
6. Do you need to authenticate a sender by public identity? Use a digital signature.
7. Do you need to hide plaintext from the DB server? Encrypt before sending to the server.

### 13.2. Do Not Choose by Function Name Alone

Having "hash" or "encrypt" in a function name does not automatically satisfy a threat model. Identify the attacker, key ownership, data lifetime, recovery, and rotation requirements.

---

## 14. Designing Tables to Store Encrypted Data

Ciphertext is typically stored in `bytea`. Tables should include enough metadata to decrypt in the future without exposing keys.

### 14.1. Illustrative Schema

~~~sql
CREATE TABLE app.protected_value (
    value_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ciphertext BYTEA NOT NULL,
    crypto_scheme TEXT NOT NULL,
    key_version INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

### 14.2. crypto_scheme

Records the format/algorithm family so you know how to process older ciphertexts. Do not allow clients to pass arbitrary algorithm names into dynamic SQL.

### 14.3. key_version

References the key version in the KMS/secret manager. Never store raw keys in this column.

### 14.4. Format Version

When needed, add a separate `format_version` column to distinguish payload formats, serialization, and encryption envelopes. Changing formats requires a migration plan.

### 14.5. Key Identifier

You may store a non-sensitive identifier to locate the key in KMS. Never store private keys, passphrases, or secret bytes.

### 14.6. Associated Metadata

PGP encryption in pgcrypto does not provide a general AEAD API accepting arbitrary associated data like some application libraries do. If you need to bind ciphertext to a tenant ID, record ID, or purpose, design an explicit authenticated context in the application protocol or use an encryption library that supports AEAD.

### 14.7. Do Not Keep Plaintext Coexisting Longer Than Necessary

When migrating to ciphertext:
1. Add ciphertext and key version columns.
2. Backfill in batches.
3. Verify decryption/round-trip.
4. Switch reads/writes to the encrypted path.
5. Remove plaintext per retention/backup policy after verification.
6. Audit logs, replicas, exports, and backups according to data lifecycle procedures.

---

## 15. Key Management: More Important Than the Function Call

A strong algorithm cannot save a compromised key.

### 15.1. Separate Keys from Ciphertext

Do not store encryption keys or passphrases in the same row or the same database as the ciphertext. If an attacker obtains a database dump, they should not have all the components needed to decrypt.

### 15.2. Use a KMS, HSM, or Secret Manager

Manage keys in a system that provides:
- Access control.
- Audit trail.
- Rotation.
- Revocation.
- Backup/recovery.
- Separation of duties.
- Per-environment/per-service policies.

### 15.3. Envelope Encryption

A common pattern:
1. Generate a random data encryption key (DEK).
2. Encrypt the data with the DEK.
3. Use a key-encryption key (KEK) in KMS to wrap the DEK.
4. Store the ciphertext and the wrapped DEK.
5. On read, KMS unwraps the DEK and then the ciphertext is decrypted.

pgcrypto can perform part of the encryption in the flow, but wrapping/unwrapping and KEK lifecycle should be handled by KMS/client services.

### 15.4. Do Not Pass Keys as SQL Literals

Do not write:

~~~sql
SELECT public.pgp_sym_decrypt(ciphertext, 'my-production-secret');
~~~

Literals can appear in source code, query history, logs, monitoring, shell history, or audits. Use bind parameters and policy-driven secret retrieval. Bind parameters reduce exposure in query text, though they do not hide the key from the PostgreSQL server when the server has to process it.

### 15.5. Key Rotation

Rotation can include:
- Creating a new key version.
- Using the new key for writes.
- Decrypting and re-encrypting older data in batches.
- Tracking the percentage of rows still using old keys.
- Revoking old keys once backup/retention and recovery requirements are met.

### 15.6. Rotation Is Not Relabeling Version Numbers

You cannot change `key_version` from 1 to 2 if the ciphertext is still encrypted with key 1. You must decrypt with the old key and encrypt with the new key.

### 15.7. Recovery and Backups

Losing a key can make data undecryptable even when database backups remain intact. Backup/recovery plans must protect key material and metadata through dedicated procedures, including real restore testing.

### 15.8. Least Privilege

Separate permissions:
- Services may only request decryption of records they require.
- Operators do not automatically have access to retrieve all keys.
- Key administrators manage KMS policies.
- Database roles have only the necessary privileges on encrypted tables/functions.

### 15.9. Key Scope

Use separate keys per environment, tenant, or purpose when strong isolation is required. Avoid a single system-wide key for every application and every dataset.

---

## 16. Search, Equality, and Indexing on Ciphertext

Encryption directly affects how data can be queried.

### 16.1. Randomized Ciphertext Does Not Support Direct Equality Search

The same plaintext can produce different ciphertexts. Therefore, comparing stored ciphertext with the output of a fresh encryption call is not a reliable search mechanism.

### 16.2. Do Not Use Deterministic Encryption Casually

Deterministic encryption leaks equality patterns: an attacker can tell that two rows hold the same value even without seeing the plaintext. It can also be vulnerable to dictionary attacks if plaintext has low entropy.

### 16.3. Blind Index

One design stores an HMAC of a normalized value using a separate key:

~~~sql
CREATE TABLE app.customer_lookup (
    customer_id BIGINT PRIMARY KEY,
    encrypted_email BYTEA NOT NULL,
    email_lookup_token BYTEA NOT NULL,
    lookup_key_version INTEGER NOT NULL
);
~~~

The token is computed via HMAC over the canonicalized email with a dedicated secret key. Equality queries compare tokens, then decrypt/verify the result if needed.

### 16.4. Blind Indexes Still Leak Information

A blind index can reveal:
- Identical values.
- Frequency distributions.
- Query patterns.
- Certain information under known-plaintext or chosen-query scenarios.

Do not use a blind index if your threat model cannot accept that leakage.

### 16.5. Separate Encryption Keys from Lookup Keys

Use different keys for ciphertext encryption and HMAC blind indexes. You can derive subkeys from a master key using a KMS-approved key derivation design, rather than inventing your own KDF.

### 16.6. Blind Index Rotation

When the lookup key changes, tokens for existing records must be recomputed. Plan a dual-read/dual-write or migration phase so search capability is not lost during the transition.

---

## 17. Server-Side pgcrypto vs. Client-Side Encryption

### 17.1. Server-Side pgcrypto

The application sends plaintext/keys to PostgreSQL functions; PostgreSQL encrypts/decrypts and returns the result.

Pros:
- Convenient SQL integration.
- Can be applied close to data access.
- Can reduce duplicated crypto logic across multiple clients.

Limitations:
- The server processes plaintext and keys.
- A DBA or host compromise can expose data.
- Queries/logging/configuration can leak inputs.
- Difficult to satisfy a zero-knowledge model with respect to database operators.

### 17.2. Client-Side Encryption

The application encrypts before sending ciphertext to PostgreSQL and decrypts after reading.

Pros:
- The DB server never needs to receive plaintext/keys.
- Can reduce trust placed in DBAs/servers.
- Key policy aligns with application identity.

Trade-offs:
- Searching, sorting, constraints, and indexing are limited.
- Clients must manage serialization and key lifecycle.
- Multiple applications must agree on formats.
- Key rotation and migration require orchestration.

### 17.3. When to Choose Which?

| Requirement | Approach |
| --- | --- |
| Need encryption within SQL workflows and DB server is trusted | Server-side pgcrypto can be suitable |
| DBAs must not read plaintext | Client-side encryption or an appropriate KMS architecture |
| Need password storage | Application password hashing or pgcrypto `crypt` per policy |
| Need controlled decryption across multiple services | KMS/envelope encryption |
| Need equality search on encrypted fields | Blind index with leakage review or specialized design |
| Need large files/streaming | Appropriate application/file encryption library |

---

## 18. TLS, Encryption at Rest, and pgcrypto

These three layers protect different boundaries.

### 18.1. TLS

TLS protects data in transit between client and server. Enabling pgcrypto does not mean connections are encrypted.

### 18.2. Storage Encryption

Disk encryption, cloud volume encryption, or backup encryption protects storage media/snapshots per the threat model. While the database server is running and has file read access, data can still be accessed through the server.

### 18.3. Column-Level Encryption

pgcrypto can encrypt individual fields prior to storage. It reduces the risk of reading plaintext from database dumps if keys are kept separate.

### 18.4. Defense in Depth

A system may require TLS, disk/backup encryption, column encryption, role grants, RLS, auditing, and key management together. No single layer replaces all the others.

---

## 19. Permissions, Schemas, and Logging

### 19.1. Function Permissions

Verify `EXECUTE` privileges on pgcrypto functions and `USAGE` privileges on the schema. Avoid granting `EXECUTE` broadly to roles that do not need it.

### 19.2. Schema Qualification

Call functions using schema-qualified names to prevent `search_path` manipulation or object shadowing.

### 19.3. SECURITY DEFINER

If wrapping pgcrypto inside a `SECURITY DEFINER` function:
- Fix a safe `search_path`.
- Schema-qualify objects.
- Control `EXECUTE` grants.
- Never allow arbitrary input to construct dynamic SQL.
- Never return plaintext to callers lacking sufficient privilege.

### 19.4. Query Logging

Do not log passwords, passphrases, keys, or sensitive plaintext. Check:
- `log_statement`.
- `log_min_duration_statement`.
- `log_parameter_max_length`.
- `log_parameter_max_length_on_error`.
- Application/APM query capture.
- Audit extension configuration.

Logging parameter names and availability depend on the PostgreSQL version.

### 19.5. Error Details

Decryption failures can emit detailed messages. Return generic errors to clients and record masked diagnostic information in secure logs.

### 19.6. Backups and Replicas

Ciphertext is replicated and backed up like normal data. Ensure backups contain ciphertext while keys remain protected separately. Review access policies for replicas, analytics exports, and support dumps.

---

## 20. Performance and Operational Limits

### 20.1. Hashing Has a Cost

digest/HMAC are generally much faster than password hashing. bcrypt is intentionally slow to raise brute-force costs; its cost parameter must be benchmarked.

### 20.2. Encryption Consumes CPU

Encrypting/decrypting per row in large queries can increase CPU usage and latency. Measure against payload size, concurrency, and query plans.

### 20.3. PGP Format Overhead

OpenPGP includes metadata, session keys, integrity information, and optionally compression. Ciphertext is larger than plaintext. Do not assume an encrypted column has the same size.

### 20.4. Do Not Use SQL Crypto for Very Large Files

pgcrypto functions accept entire values according to PostgreSQL data types. For large files or streaming workloads, use an application/file encryption library with streaming support and store encrypted objects in suitable storage.

### 20.5. Compression

PGP has compression options. Compressing before encryption is usually more effective than compressing ciphertext; ciphertext barely compresses further. Consider data sensitivity, CPU, and side-channel concerns when compressing data that mixes secrets with attacker-controlled input.

### 20.6. Connection Concurrency

High password hashing cost can cause CPU spikes when login concurrency surges. Rate-limit, queue, or perform password hashing in an application auth service.

### 20.7. Query Planner

A predicate calling `pgp_sym_decrypt` on every row can be CPU-intensive and prevent effective index usage. Design a separate blind index/search path if truly needed.

### 20.8. Resource Isolation

Monitor CPU, query duration, lock waits, memory, connection pools, and errors. Do not allow an API to let clients send huge payloads into crypto functions without limits.

---

## 21. Error Handling and Validation

### 21.1. Wrong Passphrase or Key

Decryption can fail due to a wrong key/passphrase, corrupted ciphertext, or invalid format. Do not treat every decryption error as "wrong password".

### 21.2. Truncated Ciphertext

Truncated `bytea` or faulty serialization can cause decryption failures. Check transport, schema types, and application encoding.

### 21.3. Algorithm Mismatch

Parties must agree on PGP format/options and key material. Store `crypto_scheme`/format version to choose the correct decryption path.

### 21.4. Input Validation

Limit payload length, validate encoding, and enforce authorization before decrypting. Prevent attackers from using a decryption endpoint as an arbitrary oracle.

### 21.5. Do Not Expose Raw Crypto Errors Externally

Return generic responses and avoid leaking key validity, parsing details, or data contents. Log internal error codes and correlation IDs without secrets.

### 21.6. Round-Trip Tests

For text/binary data, test:
- Plaintext → encrypt → decrypt.
- Unicode.
- Empty string/empty `bytea` if allowed by the use case.
- Null handling.
- Maximum payload size.
- Wrong key.
- Corrupted ciphertext.
- Old/new key versions.
- Cross-version compatibility.

---

## 22. Common Anti-Patterns

| Anti-pattern | Problem | Better approach |
| --- | --- | --- |
| `digest(password, 'sha256')` | Hash is too fast, easy to brute force | `crypt` bcrypt or Argon2id |
| Using md5/sha1 for new integrity checks | Inadequate collision resistance | SHA-256/512 or HMAC |
| Using `digest` instead of HMAC | Attacker can recompute after modifying payload | `hmac` with a secret key |
| Using HMAC to hide plaintext | HMAC does not encrypt | Encryption |
| Using encryption for passwords | Can be decrypted if the key leaks | Password hashing |
| Storing keys next to ciphertext | A database dump exposes both | Separate KMS/secret manager |
| Putting keys in SQL literals | Can leak via logs/history | Bind parameters + secret manager |
| Using `random()` to generate tokens | Not a CSPRNG | `gen_random_bytes` |
| Comparing ciphertexts to search plaintext | Encryption is randomized | Blind index with leakage assessment |
| Using PGP encryption to prove sender | Anyone can use a public key | Digital signature/HMAC |
| Trusting armor headers as identity | Headers are not proof of trust | Verify fingerprint/signature |
| Enabling `disable-mdc` | Disables integrity protection | Keep integrity checks enabled |
| Using one key for every purpose | Cross-purpose compromise | Key separation |
| Not storing key version | Cannot tell which key decrypts a row | Version metadata |
| Rotating keys by only changing version column | Ciphertext still uses the old key | Decrypt/re-encrypt |
| Giving DBAs keys when threat model forbids DBA access | Server-side pgcrypto sees the key | Client-side encryption |
| Encrypting large files inside SQL | Memory/CPU/size overhead | External streaming encryption |
| Never testing key restore | Backups may be undecryptable | Recovery rehearsal |

---

## 23. End-to-End Example: Payload Checksum

A checksum is suitable when you need a data fingerprint and the digest is stored or received over a trusted channel.

### 23.1. Generate a Digest

~~~sql
SELECT encode(
    public.digest(convert_to($1::text, 'UTF8'), 'sha256'),
    'hex'
) AS payload_fingerprint;
~~~

### 23.2. Compare

Recompute the digest on the received payload and compare it against the stored fingerprint.

### 23.3. Limitations

If an attacker can alter both the payload and the fingerprint, they can generate a new pair. Use HMAC or a signature if authentication is needed.

### 23.4. Store Metadata

Record the algorithm and canonicalization version so the system knows how to recompute the fingerprint when formats evolve.

---

## 24. End-to-End Example: HMAC for Webhooks

### 24.1. Payload

Assume the webhook body is received as `bytea` to preserve the exact byte sequence. Do not parse JSON and re-serialize it before verification if the sender computed the HMAC over the raw body.

### 24.2. Compute HMAC

~~~sql
SELECT public.hmac(
    $1::bytea,
    $2::bytea,
    'sha256'
);
~~~

### 24.3. Verify

Compare the received MAC with the recomputed MAC using a constant-time method in a trusted application/library. The illustrative SQL query does not replace the constant-time comparison requirement across a timing-observable security boundary.

### 24.4. Replay Protection

Verify a timestamp/signature window, nonce, or event ID and store processed events. A valid HMAC alone does not prevent an old webhook from being replayed.

### 24.5. Key Rotation

You can maintain both the current key and previous key briefly during rotation, paired with a non-sensitive key identifier. Revoke the old key once the compatibility window closes.

---

## 25. End-to-End Example: Password Authentication

### 25.1. Create Hash

~~~sql
INSERT INTO app_user_auth (
    user_id,
    username,
    password_hash
)
VALUES (
    $1,
    $2,
    public.crypt($3, public.gen_salt('bf', 12))
);
~~~

### 25.2. Verify

~~~sql
SELECT password_hash = public.crypt($1, password_hash)
FROM app_user_auth
WHERE username = $2;
~~~

### 25.3. Rate Limiting

Enforce rate limits at the auth service/API, per user and network risk. A high hash cost alone does not prevent credential stuffing if an endpoint allows unlimited requests.

### 25.4. Rehash

After verifying a valid password, if the old cost is below policy, generate a new hash and update it within a transaction.

### 25.5. Do Not Log Input

Do not log password bind parameters or request bodies containing credentials. Check APM/error capture settings.

---

## 26. End-to-End Example: Encrypting a Sensitive Field

### 26.1. Table

~~~sql
CREATE TABLE app.customer_private_data (
    customer_id BIGINT PRIMARY KEY,
    encrypted_tax_id BYTEA NOT NULL,
    key_version INTEGER NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

### 26.2. Insert Ciphertext

~~~sql
INSERT INTO app.customer_private_data (
    customer_id,
    encrypted_tax_id,
    key_version
)
VALUES (
    $1,
    public.pgp_sym_encrypt($2::text, $3::text),
    $4
);
~~~

`$3` is a passphrase/key passed through a secret flow; this example does not endorse storing keys in SQL source or database tables.

### 26.3. Authorized Decryption

~~~sql
SELECT public.pgp_sym_decrypt(encrypted_tax_id, $1::text)
FROM app.customer_private_data
WHERE customer_id = $2;
~~~

Only the service role should be permitted to call the decryption path. Consider wrapping it in a function with explicit authorization that never returns plaintext to unauthorized roles.

### 26.4. Store Key Version

When reading a row, the application uses `key_version` to fetch the appropriate key from the KMS/secret manager. Do not use a single hard-coded key for all versions.

### 26.5. Handling Search

Avoid searching by decrypting the entire table on the request path whenever possible. If exact-match lookup is required, evaluate a blind index with a separate HMAC key and explicitly accept the equality leakage.

---

## 27. Key Rotation Procedure

### Step 1: Prepare the New Key

Create a new key version in the KMS/secret manager and configure its policy and access permissions.

### Step 2: Start Writes with the New Key

The application writes new ciphertexts alongside the new `key_version`.

### Step 3: Read Legacy Data by Version

When reading a row, select the key based on metadata. Do not try every key sequentially if the version can be determined.

### Step 4: Re-Encrypt in Batches

1. Read the old ciphertext.
2. Decrypt with the old key.
3. Encrypt with the new key.
4. Update `ciphertext` and `key_version` atomically.
5. Commit the batch.
6. Record progress/idempotency markers.

### Step 5: Verify

Count rows by `key_version`; test sample decryption and check application workflows. Monitor decryption errors and latency.

### Step 6: Backups and Retention

Confirm that necessary backups can still be restored using the old key throughout the retention window. Do not revoke the old key before legitimate restore needs expire.

### Step 7: Revoke the Old Key

Once all data, replicas, exports, and backups have been handled per policy, revoke the old key and retain audit evidence.

### Step 8: Blind Index Rotation

If the lookup HMAC key also changes, plan token recomputation and dual-read/dual-write during the transition period.

---

## 28. Lab 1: Installing pgcrypto and Using digest

Use a development/staging database.

### 28.1. Check the Package

~~~sql
SELECT *
FROM pg_catalog.pg_available_extensions
WHERE name = 'pgcrypto';
~~~

### 28.2. Install the Extension

~~~sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
~~~

### 28.3. Generate SHA-256

~~~sql
SELECT encode(public.digest('hello', 'sha256'), 'hex');
~~~

### 28.4. Test Encoding

~~~sql
SELECT encode(
    public.digest(convert_to('Hello PostgreSQL', 'UTF8'), 'sha256'),
    'hex'
);
~~~

### 28.5. Compare Two Payloads

Compute digests for two different strings and observe the differing outputs. Do not use this lab to claim that a hash proves sender identity.

### 28.6. Conclusion

`digest` produces a one-way fingerprint and returns `bytea`; `encode` only converts the representation for display.

---

## 29. Lab 2: HMAC and Integrity Verification

### 29.1. Prepare a Test Key

Use a dummy key in the lab environment; never use a production secret. In real applications, pass keys via bind parameters.

### 29.2. Generate HMAC

~~~sql
SELECT encode(
    public.hmac(
        convert_to('event=created&id=42', 'UTF8'),
        decode($1, 'hex'),
        'sha256'
    ),
    'hex'
);
~~~

`$1` is the test key in hex format.

### 29.3. Modify the Payload

Compute the HMAC for a payload with one byte/character changed and observe how the MAC changes.

### 29.4. Change the Key

Use a different key and observe that the MAC does not match.

### 29.5. Discuss Replay

Re-sending the exact old payload and MAC still produces a valid pair. Design timestamps/nonces/event IDs to prevent replay.

### 29.6. Conclusion

HMAC requires a shared secret and key protection. It authenticates the payload but does not encrypt it.

---

## 30. Lab 3: Password Hashing with crypt

### 30.1. Create a Test Hash

~~~sql
SELECT public.crypt(
    'Lab-only-password',
    public.gen_salt('bf', 10)
) AS password_hash;
~~~

Cost 10 is for lab use only; production requires benchmarking and policy alignment.

### 30.2. Verify Correct Password

~~~sql
SELECT
    public.crypt('Lab-only-password', password_hash) = password_hash
FROM (
    SELECT public.crypt(
        'Lab-only-password',
        public.gen_salt('bf', 10)
    ) AS password_hash
) AS test_data;
~~~

### 30.3. Verify Wrong Password

Replace the input with a different password. The result must be `false`.

### 30.4. Compare Costs

Generate hashes with different cost parameters and measure execution time in the lab environment. Do not run CPU-exhausting benchmarks on production.

### 30.5. Discuss Bcrypt Length

Examine UTF-8 byte length and the 72-byte limit. Propose how to handle long passwords per application policy.

### 30.6. Conclusion

`crypt` uses the stored salt/setting to verify passwords. Never substitute a fast `digest`.

---

## 31. Lab 4: Symmetric Encryption and Binary Data

### 31.1. Encrypt Text

~~~sql
SELECT public.pgp_sym_encrypt(
    'Sensitive lab note',
    $1::text
);
~~~

Use a dummy passphrase in the lab.

### 31.2. Decrypt

~~~sql
SELECT public.pgp_sym_decrypt(
    $1::bytea,
    $2::text
);
~~~

### 31.3. Test Wrong Passphrase

Use a different passphrase and observe the error. Never return raw error details to end users in an application.

### 31.4. Test bytea

~~~sql
SELECT public.pgp_sym_encrypt_bytea(
    decode('000102ff', 'hex'),
    $1::text
);
~~~

Then use `pgp_sym_decrypt_bytea` and encode the result to verify the bytes match.

### 31.5. Inspect Ciphertext Size

Compare `octet_length` of plaintext and ciphertext. PGP packet metadata adds overhead to the ciphertext.

### 31.6. Conclusion

Use the text or bytea API matching the data type and manage passphrases outside the database.

---

## 32. Lab 5: Public-Key Encryption and Armor

This lab requires a test PGP key pair generated by an approved OpenPGP tool. Never generate or use production private keys in a lab.

### 32.1. Obtain Armored Public Key

Supply the test armored public key via a bind parameter or a secure fixture.

### 32.2. Encrypt

~~~sql
SELECT public.pgp_pub_encrypt(
    'Message for lab recipient',
    public.dearmor($1::text)
);
~~~

### 32.3. Armor Ciphertext

~~~sql
SELECT public.armor($1::bytea);
~~~

### 32.4. Read Headers

~~~sql
SELECT *
FROM public.pgp_armor_headers($1::text);
~~~

### 32.5. Decrypt

~~~sql
SELECT public.pgp_pub_decrypt(
    $1::bytea,
    public.dearmor($2::text),
    $3::text
);
~~~

`$2` is the test armored private key; `$3` is the private-key passphrase if set.

### 32.6. Verify Identity

Use the fingerprint from the OpenPGP key management tool to verify the public key. Do not rely on armor headers or key IDs alone.

### 32.7. Conclusion

Public-key encryption solves encrypting for a recipient; it does not automatically create a signature authenticating the sender.

---

## 33. Practice Exercises

### Exercise 1 — Primitive Selection

Distinguish `digest`, HMAC, password hash, symmetric encryption, and public-key encryption.

### Exercise 2 — Threat Model

A DBA has superuser privileges. Does server-side pgcrypto protect plaintext from the DBA? Explain.

### Exercise 3 — Installation

Write the commands to check for the pgcrypto package, install the extension, and verify its schema/version.

### Exercise 4 — Multi-Database

Why must `CREATE EXTENSION pgcrypto` be executed in each database where it is needed?

### Exercise 5 — Digest

Write a query to generate a SHA-256 hash for UTF-8 text and display it in hex.

### Exercise 6 — Digest Algorithms

Compare MD5, SHA-1, SHA-256, and SHA-512. Which algorithms are suitable for new fingerprints?

### Exercise 7 — Canonicalization

Two systems hash the same JSON and get different outputs. List potential causes and how to normalize them.

### Exercise 8 — Hash Integrity

An attacker can modify both the payload and the digest. Why does `digest` fail to stop this attacker?

### Exercise 9 — HMAC

Write a query to generate HMAC-SHA256 from a `bytea` payload and a key bind parameter.

### Exercise 10 — HMAC vs. Encryption

Why does HMAC not keep the payload confidential?

### Exercise 11 — Replay

A webhook with a valid HMAC is re-sent. Design a nonce/timestamp/event ID scheme to prevent replay.

### Exercise 12 — Key Management

Propose where to store HMAC keys and how to assign service permissions.

### Exercise 13 — Password Hashing

Write an `INSERT` using `crypt` and `gen_salt('bf', cost)` to store a password hash.

### Exercise 14 — Password Verification

Write a query to verify a password against a stored hash.

### Exercise 15 — Cost

Explain how bcrypt cost affects computation time and how to benchmark it.

### Exercise 16 — Password Schemes

Why should DES/xdes/MD5 schemes in `crypt` not be used for new systems?

### Exercise 17 — Bcrypt Length

Explain the 72-byte limit and why byte count differs from Unicode character count.

### Exercise 18 — Argon2id

Does pgcrypto provide Argon2id? If policy requires Argon2id, where should password hashing live?

### Exercise 19 — Randomness

Write a query to generate 32 random bytes and encode them into a text token.

### Exercise 20 — random()

Why is `random()` unsuitable for generating reset tokens or encryption keys?

### Exercise 21 — Symmetric Encryption

Write an example of `pgp_sym_encrypt` and `pgp_sym_decrypt` for a text field.

### Exercise 22 — Binary Encryption

Distinguish `pgp_sym_encrypt` from `pgp_sym_encrypt_bytea`.

### Exercise 23 — Cipher Options

State what needs to be verified before specifying `cipher-algo=aes256`.

### Exercise 24 — PGP Integrity

What does MDC/integrity protection solve? Why does it not prove the sender's identity?

### Exercise 25 — Public-Key Encryption

Explain which party uses the public key to encrypt and which party uses the private key to decrypt.

### Exercise 26 — Digital Signatures

Why does `pgp_pub_encrypt` not replace a digital signature?

### Exercise 27 — Armor

Write a query to armor ciphertext and dearmor text back to `bytea`.

### Exercise 28 — Key ID

What is `pgp_key_id` useful for, and why is a full fingerprint more trustworthy for verifying identity?

### Exercise 29 — Key Separation

Design separate keys for encryption and an HMAC blind index.

### Exercise 30 — Envelope Encryption

Describe DEK, KEK, wrapping/unwrapping, and the role of KMS.

### Exercise 31 — Key Rotation

Write the steps to re-encrypt ciphertext from key version 1 to version 2.

### Exercise 32 — Backup Recovery

Why is a database backup insufficient if an old key version has been revoked or lost?

### Exercise 33 — Searching Encrypted Fields

Why cannot PGP ciphertext be used directly for equality lookups?

### Exercise 34 — Blind Index

Design an HMAC lookup token for email. Note equality leakage and key rotation requirements.

### Exercise 35 — DBA Threat

A requirement states DBAs must not view plaintext. Compare server-side pgcrypto with client-side encryption.

### Exercise 36 — Logging

List places where passwords, passphrases, or keys can be logged unintentionally.

### Exercise 37 — Performance

A query decrypting 10 million rows is very slow. Describe how to redesign the access path and limit decryption.

### Exercise 38 — PGP Key Lifecycle

Design a workflow for generating, verifying fingerprints, storing private keys, revoking, and rotating key pairs.

### Exercise 39 — Failure Handling

Design an API response when decryption fails without leaking information about keys or ciphertext.

### Exercise 40 — End-to-End Design

An application stores passwords, webhook payloads, searchable emails, and tax IDs that require encryption. Choose primitives for each type, design key separation/KMS, schema, rotation, logging, permissions, backup recovery, and a test plan. Explain why a single pgcrypto function cannot handle all of them.

---

## 34. pgcrypto Operational Checklist

| Item | What to verify |
| --- | --- |
| Use case | Confidentiality, integrity, password verification, or randomness |
| Threat model | Who must be prevented from reading/modifying data |
| PostgreSQL version | Source/target major version |
| OpenSSL | Build/package supports pgcrypto |
| Extension | Package is available and extension is installed in the right database |
| Extension schema | Actual schema and qualified function names |
| Function grants | `EXECUTE`/`USAGE` per least privilege |
| Digest | Modern algorithm and canonical input |
| HMAC | Key entropy, purpose separation, and rotation |
| Password | bcrypt cost benchmark or Argon2id policy |
| Bcrypt length | Password UTF-8 byte length and 72-byte behavior |
| Randomness | `gen_random_bytes`, not `random()` |
| Encryption | Text/bytea function matching the data type |
| PGP options | Cipher, S2K, and integrity protection |
| Public/private keys | Fingerprint verification and ownership |
| Digital signatures | Separate signing/verification solution if needed |
| Key management | External KMS/HSM/secret manager outside the DB |
| Key separation | Distinct encryption and HMAC keys |
| Key version | Metadata attached to ciphertext |
| Rotation | Re-encryption and recovery window |
| Search | Blind index leakage evaluated |
| Client/server boundary | Whether the DB server sees plaintext/keys |
| TLS | Connection transport is protected |
| Storage/backups | Ciphertext and key backups separated |
| Logging | Queries/errors/APM do not contain secrets |
| Permissions | Roles have no decryption privilege beyond necessity |
| SECURITY DEFINER | Safe `search_path` and object qualification |
| Performance | CPU, payload size, concurrency, and latency |
| Input validation | Size, encoding, and decryption authorization |
| Error handling | Do not expose crypto internals to clients |
| Compatibility | Cipher/format compatible across source and target |
| Restore test | Able to retrieve keys and decrypt backup samples |
| Audit | Who accessed keys, decrypted, and rotated |
| Incident response | Revoke/rotate on key compromise |

## Conclusion

pgcrypto provides useful cryptographic building blocks inside PostgreSQL: `digest` creates fingerprints, HMAC authenticates data using a shared secret, `crypt`/`gen_salt` store password hashes, `gen_random_bytes` generates random bytes, and the `pgp` functions encrypt/decrypt data per OpenPGP.

Key principles to remember:

1. **Choose the primitive by goal.** Hashing, HMAC, password hashing, encryption, and randomness solve different problems.
2. **digest is not HMAC.** An unkeyed digest does not prevent an attacker from recomputing the hash after modifying the payload.
3. **HMAC does not encrypt.** It authenticates data with a shared secret while leaving plaintext readable.
4. **Never use SHA-256 to store passwords.** Use password hashing with salt/cost such as bcrypt or Argon2id per policy.
5. **Bcrypt has a 72-byte input limit.** Account for UTF-8 byte length and policy for long passwords.
6. **Use a CSPRNG for tokens and key material.** `gen_random_bytes` is appropriate instead of `random()`.
7. **PGP encryption needs strong, managed keys.** Never store passphrases or private keys next to ciphertext.
8. **Public-key encryption is not a digital signature.** It encrypts for the recipient without verifying the sender.
9. **pgcrypto runs inside the server.** PostgreSQL processes plaintext/keys; if DBAs must not see plaintext, consider client-side encryption.
10. **Key management is mandatory.** Use a KMS/HSM/secret manager, key versions, separation, and rotation.
11. **Randomized ciphertext does not support direct equality search.** A blind index can help, but it leaks equality/frequency patterns.
12. **TLS and encryption at rest remain necessary.** pgcrypto does not replace transport or storage protections.
13. **Never put secrets in SQL literals or logs.** Use bind parameters and control query/error capture.
14. **Test recovery alongside the key lifecycle.** A backup is only useful if the required keys remain accessible per policy.
15. **Measure performance on real workloads.** Password hashing, encryption, and decryption all incur CPU cost and can impact concurrency.

A sound pgcrypto design starts with a threat model, selects the right primitive, keeps keys outside the database when required, stores metadata sufficient for rotation, and verifies the read, write, backup, and recovery paths end to end. Cryptographic functions are only one part of the system; security depends on how keys, permissions, logs, and applications are managed together.
