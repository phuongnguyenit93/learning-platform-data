# The keytool Command in Java

`keytool` is a command-line tool bundled with the JDK for managing key pairs, certificates, certificate chains, and keystores. This tool is commonly used when configuring TLS/HTTPS, preparing server certificates, managing truststores, signing or verifying artifacts, and converting security data between keystore formats.

This lesson uses JDK 17 or later. You will practice generating key pairs, inspecting certificates, exporting public certificates, creating a Certificate Signing Request (CSR), importing CA-signed certificates, managing truststores, and protecting keystores. The sample commands use PKCS12 and let `keytool` prompt for passwords interactively, avoiding recording real passwords in shell history.

## 1. What is keytool used for?

`keytool` manages security data stored in a keystore. Main tasks include:

- Generating public/private key pairs.
- Creating self-signed certificates for testing or use in controlled environments.
- Generating a CSR to send to a Certificate Authority (CA) for signing.
- Importing certificates or certificate chains.
- Exporting public certificates for exchange.
- Viewing certificate details, fingerprints, and validity periods.
- Migrating entries between keystores.
- Changing passwords, renaming aliases, or deleting entries.
- Managing secret keys used for certain symmetric encryption tasks.

An X.509 certificate is data signed by an issuer that binds a public key to subject information. The private key is kept secret and used for operations such as signing or proving key ownership; the public key can be distributed along with the certificate.

`keytool` is a key and certificate management tool. It does not automatically make a self-signed certificate trusted by browsers or operating systems. Trust depends on trust anchors and the policies of the application/environment.

## 2. Keystore, truststore, and entry types

### 2.1. Keystore and truststore

Both keystores and truststores are repositories accessed through the `KeyStore` API. The main difference lies in their intended use:

| Store | Typical contents | Purpose |
|---|---|---|
| Keystore | The application/server's own private key and certificate chain | Proving the identity of the application or server |
| Truststore | Certificates of CAs or peers that the application trusts | Verifying the certificates of other servers/peers |

A TLS server application typically needs a keystore containing the server's private key and certificate. A TLS client application may need a truststore containing the CAs that the client accepts.

Keystore and truststore are not two different file formats. Both can use PKCS12 or JKS; their role is determined by how the application uses the contents inside.

### 2.2. Three common entry types

| Entry type | Contents | Example |
|---|---|---|
| `PrivateKeyEntry` | A private key and its corresponding certificate chain | Server TLS key |
| `trustedCertEntry` | A certificate configured as trusted | Root CA in a truststore |
| `SecretKeyEntry` | A secret key used for symmetric encryption | AES key |

Each entry is identified by an alias. The alias must accurately identify the entry when using `-list`, `-exportcert`, `-importcert`, `-delete`, or other management commands.

## 3. Keystore formats: PKCS12 and JKS

In JDK 9 and later, the standard default keystore type is `PKCS12`. This is a widely adopted format that provides interoperability across platforms and tools.

`JKS` is Java's traditional keystore format. The JDK still supports JKS for compatibility with legacy systems.

| Format | Characteristics | When to use |
|---|---|---|
| `PKCS12` | Widely used interchange standard supporting private keys and certificates | Recommended default choice for new projects |
| `JKS` | Java's traditional keystore format | Compatibility with legacy systems requiring JKS |

You should explicitly specify `-storetype PKCS12` or `-storetype JKS` in important commands to avoid depending on environment configuration.

The `.p12`, `.pfx`, or `.jks` extensions are only naming conventions. The actual keystore type is determined by the data format and the `-storetype` option, not solely by the file extension.

## 4. General syntax and viewing help

General syntax:

~~~text
keytool <command> [options]
~~~

Each invocation of `keytool` executes only one command. The options for that command can appear in various orders.

View the list of commands:

~~~powershell
keytool -help
~~~

View help for a specific command:

~~~powershell
keytool -list -help
keytool -genkeypair -help
keytool -importcert -help
~~~

Some common options:

| Option | Meaning |
|---|---|
| `-alias` | Name of the entry to create or operate on |
| `-keystore` | Path to the keystore file |
| `-storetype` | Keystore format, such as `PKCS12` or `JKS` |
| `-storepass` | Password protecting the keystore |
| `-keypass` | Password protecting the entry's private/secret key |
| `-file` | Certificate, CSR, or input/output data file |
| `-dname` | Subject's Distinguished Name |
| `-validity` | Number of days the certificate is valid |
| `-keyalg` | Algorithm for generating the key pair |
| `-keysize` | Key size |
| `-ext` | X.509 certificate extension |
| `-v` | Display verbose information |

If an option value contains spaces, enclose the value in double quotes. Do not put real passwords in examples, scripts, or command history; when no password is passed, `keytool` will prompt in the terminal.

## 5. Creating a keystore and key pair with -genkeypair

`-genkeypair` generates a public/private key pair. If no signer is specified, `keytool` creates a self-signed X.509 v3 certificate containing the public key and stores the private key along with a single-element certificate chain in the keystore.

Example of creating a PKCS12 keystore for a local development environment:

~~~powershell
keytool -genkeypair `
  -alias local-server `
  -keyalg RSA `
  -keysize 3072 `
  -storetype PKCS12 `
  -keystore server.p12 `
  -validity 365 `
  -dname "CN=localhost, OU=Development, O=Example, L=Ho Chi Minh City, C=VN" `
  -ext "SAN=dns:localhost,ip:127.0.0.1"
~~~

In PowerShell, the backtick at the end of a line continues a multi-line command. You can also write the command above on a single line.

Explanation:

- `-alias local-server`: names the entry `local-server`.
- `-keyalg RSA`: uses the RSA algorithm.
- `-keysize 3072`: generates a 3072-bit RSA key.
- `-storetype PKCS12`: selects the PKCS12 format.
- `-keystore server.p12`: creates or opens the keystore file.
- `-validity 365`: sets the self-signed certificate validity to 365 days.
- `-dname`: the subject's Distinguished Name information.
- `-ext "SAN=..."`: declares the Subject Alternative Name for the hostname and IP used in the example.

When run, `keytool` prompts for the keystore password and may prompt for the private key password. If you press Enter at the private key password prompt as instructed, the key password will use the same password as the keystore. `keytool` requires a key password of at least six characters; in practice, choose a strong, unique passphrase.

The self-signed certificate in the example is only suitable for local development or controlled testing environments. It is not automatically trusted by operating systems, browsers, or external clients.

### Why is SAN important?

`SAN` (Subject Alternative Name) records the DNS names or IP addresses that the certificate represents. When performing TLS hostname verification, modern clients typically check the SAN; specifying only `CN=localhost` does not replace declaring a SAN.

If a server is accessed via `api.example.test`, the certificate needs a SAN matching the actual name the client uses. Do not copy a `localhost` SAN into a production certificate.

## 6. Listing entries with -list

List entries in a keystore:

~~~powershell
keytool -list -keystore server.p12 -storetype PKCS12
~~~

View details of a specific alias:

~~~powershell
keytool -list -v -alias local-server -keystore server.p12 -storetype PKCS12
~~~

Commonly displayed information:

- Alias name.
- Entry type, such as `PrivateKeyEntry`.
- Entry creation date.
- Number of certificates in the chain.
- Subject and issuer.
- `Valid from` / `until` validity period.
- SHA-256 fingerprint.

You can use `-rfc` to display the certificate in PEM/Base64 format:

~~~powershell
keytool -list -rfc -alias local-server -keystore server.p12 -storetype PKCS12
~~~

If the alias does not exist, check the alias spelling, the keystore file path, and the `-storetype`.

## 7. Viewing a certificate with -printcert

`-printcert` reads a certificate from a file and prints its information:

~~~powershell
keytool -printcert -file local-server.pem
~~~

You can view more details:

~~~powershell
keytool -printcert -v -file local-server.pem
~~~

To view a server certificate without exporting it to a file first:

~~~powershell
keytool -printcert -sslserver example.com:443
~~~

Fields to inspect:

| Field | Meaning |
|---|---|
| Owner/Subject | Identity described by the certificate |
| Issuer | CA or entity that signed the certificate |
| Serial Number | Serial number assigned by the issuer |
| Valid from/until | Time period during which the certificate is valid |
| SHA-256 fingerprint | Fingerprint used to verify and compare the certificate |
| Subject Alternative Name | DNS names/IPs represented by the certificate |
| Key Usage / Extended Key Usage | Permitted purposes for using the key |

`-printcert` only displays certificate data. Seeing a certificate or seeing that its validity period is still active does not by itself prove the certificate is trustworthy. You must verify the chain, hostname, validity period, and issuing source.

## 8. Exporting a public certificate with -exportcert

`-exportcert` exports the certificate associated with an alias. Example of exporting the server's certificate to PEM:

~~~powershell
keytool -exportcert -rfc `
  -alias local-server `
  -keystore server.p12 `
  -storetype PKCS12 `
  -file local-server.pem
~~~

The `-rfc` option produces PEM text format, typically starting with:

~~~text
-----BEGIN CERTIFICATE-----
...
-----END CERTIFICATE-----
~~~

If `-rfc` is omitted, the default output is binary DER data.

This command only exports the certificate/public key; it does not export the private key. Never send a private key or a keystore file containing a private key to someone who only needs to verify a public certificate.

Verify the exported file:

~~~powershell
keytool -printcert -file local-server.pem
~~~

## 9. Creating a Certificate Signing Request with -certreq

In production environments, organizations typically do not use self-signed certificates for public-facing servers. Instead, the server generates its own key pair and sends a CSR to a CA.

A CSR contains the public key along with subject information and requested extensions. The private key remains in the server's keystore.

Generate a CSR from an existing alias:

~~~powershell
keytool -certreq `
  -alias local-server `
  -keystore server.p12 `
  -storetype PKCS12 `
  -file local-server.csr `
  -ext "SAN=dns:localhost,ip:127.0.0.1"
~~~

Inspect the CSR contents:

~~~powershell
keytool -printcertreq -file local-server.csr
~~~

Workflow:

1. Generate a key pair in the keystore.
2. Use `-certreq` to create a CSR from the alias holding the private key.
3. Submit the CSR to the CA following your organization's process.
4. The CA verifies the request and returns the certificate along with any intermediate certificates.
5. Import the CA certificates that need to be trusted into the appropriate keystore/truststore.
6. Import the certificate reply under the exact alias used to generate the key pair.
7. Verify the certificate chain using `-list -v`.

A CA may apply its own policies to the subject and extensions in a CSR. Do not assume the CA will preserve every extension; verify that the issued certificate has the required SAN and key usages.

## 10. Importing certificates and certificate chains with -importcert

`-importcert` has two main use cases:

- Importing a trusted certificate into a new alias.
- Importing a CA-issued certificate reply into an alias that holds a private key.

### 10.1. Importing a CA certificate into a truststore

Before trusting a CA certificate, inspect its fingerprint:

~~~powershell
keytool -printcert -file company-root.pem
~~~

Compare the SHA-256 fingerprint against a value obtained from an independent, trusted channel, such as verified internal documentation or a CA administrator. Do not blindly trust a certificate sent in the same email or over an unverified channel.

After confirming the fingerprint, import it into the application's dedicated truststore:

~~~powershell
keytool -importcert `
  -alias company-root `
  -file company-root.pem `
  -keystore app-truststore.p12 `
  -storetype PKCS12
~~~

`keytool` will display the details and ask for confirmation before adding the trusted certificate. Only accept after verifying the exact certificate.

### 10.2. Importing a CA reply into a private-key entry

When the CA returns the certificate chain for the server, import the certificate reply into the exact alias used to create the CSR:

~~~powershell
keytool -importcert `
  -alias local-server `
  -file server-reply.p7b `
  -keystore server.p12 `
  -storetype PKCS12 `
  -trustcacerts
~~~

Here `local-server` must be the alias containing the private key that generated the CSR. The public key in the certificate reply must match the public key of that entry. When valid, the old self-signed certificate is replaced by the CA-issued certificate chain.

If an internal CA is not yet trusted via `cacerts`, establish the trust anchor according to your organization's process before importing the certificate reply. You can import the CA certificate into the same keystore or configure an appropriate truststore. Never import an unverified certificate just to make the command succeed.

### 10.3. Distinguishing aliases when importing

| Specified alias | How `keytool` interprets the operation |
|---|---|
| Alias does not exist yet | Adds a trusted certificate entry |
| Alias is an existing key entry | Imports the certificate reply, replacing the private-key entry's chain |

Do not use a new alias when the goal is to update the certificate for an existing private key. Using the wrong alias may create a separate trusted certificate entry without updating the server's chain.

`-noprompt` disables the confirmation prompt. Do not use this option for unverified certificates or in interactive workflows where fingerprint inspection is required.

## 11. Managing truststores and cacerts

The JDK ships with a system truststore named `cacerts`, which contains a default set of root CAs. You can list its contents:

~~~powershell
keytool -list -cacerts
~~~

View details:

~~~powershell
keytool -list -v -cacerts
~~~

`-cacerts` instructs `keytool` to operate on the `cacerts` store; do not combine this option with `-keystore` or `-storetype` in the same command.

Common paths for `cacerts` are:

- Windows: `JAVA_HOME\lib\security\cacerts`
- Linux/macOS: `JAVA_HOME/lib/security/cacerts`

`cacerts` is a shared JDK truststore. Modifying it can affect multiple applications using the same runtime. For applications that need their own trust policy, create a dedicated truststore instead of modifying the system-wide truststore directly.

If a CA certificate is no longer trusted, an administrator can remove the entry with `-delete` after assessing the impact. Do not delete a root CA from `cacerts` based solely on its alias name without verifying the corresponding certificate.

## 12. Converting keystores with -importkeystore

You can migrate entries from JKS to PKCS12 or from another keystore to a target format.

Example of migrating all entries from JKS to PKCS12:

~~~powershell
keytool -importkeystore `
  -srckeystore legacy.jks `
  -srcstoretype JKS `
  -destkeystore migrated.p12 `
  -deststoretype PKCS12
~~~

`keytool` will prompt for the source and destination passwords as needed. After conversion, list both files to compare aliases, entry types, and certificate chains:

~~~powershell
keytool -list -v -keystore legacy.jks -storetype JKS
keytool -list -v -keystore migrated.p12 -storetype PKCS12
~~~

You can migrate a specific alias with `-srcalias` and assign a new alias with `-destalias`.

Some external tools require the password of a private key entry in PKCS12 to match the store password. If compatibility with such a tool is required, set `-destkeypass` equal to `-deststorepass` as required by the target tool.

Do not delete the old keystore immediately after conversion. First inspect the new file, test loading it with the actual application, and keep a safe backup until the migration is verified.

## 13. Managing aliases, passwords, and deleting entries

Common management commands:

| Command | Function |
|---|---|
| `-storepasswd` | Change the password protecting the keystore |
| `-keypasswd` | Change the password protecting a private/secret key entry |
| `-changealias` | Rename an alias |
| `-delete` | Delete an entry |

Change the keystore password:

~~~powershell
keytool -storepasswd -keystore server.p12 -storetype PKCS12
~~~

Change a private key entry password:

~~~powershell
keytool -keypasswd -alias local-server -keystore server.p12 -storetype PKCS12
~~~

Rename an alias:

~~~powershell
keytool -changealias `
  -alias local-server `
  -destalias api-server `
  -keystore server.p12 `
  -storetype PKCS12
~~~

Delete an entry:

~~~powershell
keytool -delete -alias old-entry -keystore server.p12 -storetype PKCS12
~~~

Commands that modify data should be executed only after confirming the exact file and alias. Back up the keystore before changing passwords, renaming aliases, or deleting entries. Deleting a `PrivateKeyEntry` can leave the server without the private key needed for TLS authentication.

## 14. Other keytool commands

Beyond the key pair and certificate workflow, `keytool` also supports:

| Command | Purpose |
|---|---|
| `-genseckey` | Generate a secret key and store it as a `SecretKeyEntry` |
| `-gencert` | Sign a CSR and generate a certificate; commonly used when operating a CA |
| `-importpass` | Import a passphrase as a secret-key entry |
| `-printcertreq` | Display the contents of a CSR |
| `-printcrl` | Display a Certificate Revocation List |
| `-showinfo` | Display information related to security providers/runtime |

`-gencert` requires a signer alias pointing to a private-key entry authorized to sign certificates. Do not use it as a substitute for a public CA; operating a CA requires protecting the signing key, identity verification procedures, certificate policies, and issuance controls.

## 15. End-to-end practice workflow: creating and inspecting a local certificate

The following example creates a self-signed certificate for `localhost`, inspects the entry, and exports the public certificate. Perform these steps in a test project directory.

Create the key pair and keystore:

~~~powershell
keytool -genkeypair -alias local-server -keyalg RSA -keysize 3072 -storetype PKCS12 -keystore server.p12 -validity 365 -dname "CN=localhost, OU=Development, O=Example, L=Ho Chi Minh City, C=VN" -ext "SAN=dns:localhost,ip:127.0.0.1"
~~~

List the entry:

~~~powershell
keytool -list -v -alias local-server -keystore server.p12 -storetype PKCS12
~~~

Export the public certificate:

~~~powershell
keytool -exportcert -rfc -alias local-server -keystore server.p12 -storetype PKCS12 -file local-server.pem
~~~

Read the exported certificate:

~~~powershell
keytool -printcert -file local-server.pem
~~~

Specific values for serial number, fingerprint, validity period, and encoding depend on each key pair generation run. Inspect the actual fields rather than comparing against a fixed fingerprint in documentation.

If CA signing is needed instead of a self-signed certificate, generate a CSR from that alias:

~~~powershell
keytool -certreq -alias local-server -keystore server.p12 -storetype PKCS12 -file local-server.csr -ext "SAN=dns:localhost,ip:127.0.0.1"
~~~

After the CA returns the certificate reply, verify the CA chain and import it into the `local-server` alias as shown in section 10.2.

## 16. Security when using keytool

A keystore can contain private keys or secret keys. Treat it as sensitive data:

- Do not commit keystore files containing private keys to Git or send them over standard chat/email channels.
- Do not pass real `-storepass` or `-keypass` values directly on the command line, in scripts, or in logs. `keytool` can prompt for passwords when password options are omitted.
- Use strong, distinct passphrases across environments; store them in a secret manager or your organization's secret management system.
- Restrict read permissions on the keystore file to the account running the application.
- Maintain encrypted backups and a recovery procedure.
- Verify the alias, entry type, certificate chain, SAN, validity period, and fingerprint before deployment.
- Verify the CA certificate's fingerprint through an independent channel before importing it as a trusted certificate.
- Do not use `-noprompt` to bypass certificate verification.
- Do not use a local self-signed certificate as a public production certificate.
- Do not modify the shared `cacerts` store if an application only needs its own truststore.

Passwords passed directly on the command line can appear in process listings, shell history, or logs. For automation, use your build environment's protected secret injection mechanism rather than hard-coding values.

## 17. Common errors and troubleshooting

| Symptom | Common cause | Resolution |
|---|---|---|
| `keytool is not recognized` | JDK `bin` is not on PATH or using a runtime without the tool | Install an appropriate JDK and invoke `keytool` from the `bin` directory |
| `Keystore was tampered with, or password was incorrect` | Wrong store password or wrong keystore type | Verify the password, file, and `-storetype` |
| `Alias ... does not exist` | Wrong alias or opening the wrong keystore | Use `-list` to check the alias and verify the file path |
| `Alias ... already exists` | Importing a trusted certificate into an existing alias | Choose a new alias or confirm the proper operation for updating a certificate reply |
| `Certificate reply does not contain public key for ...` | Certificate reply does not match the key pair that generated the CSR | Regenerate the CSR from the correct alias or ask the CA to reissue the certificate for the right public key |
| `Failed to establish chain from reply` | Missing intermediate/root CA or trust anchor not found | Import the proper CA chain and use a verified trust anchor |
| Certificate expired or not yet valid | Incorrect system clock or certificate outside validity period | Check the system clock and issue/import a valid certificate |
| Hostname verification failed | SAN does not include the DNS/IP used by the client | Reissue the certificate with a SAN matching the hostname/IP |
| `Unrecognized keystore format` | Wrong `-storetype` or the file is not a valid keystore | Identify the source format and specify the matching `-storetype` |
| Unable to write keystore | Directory lacks write permissions or file is locked | Check file permissions, path, and processes using the file |
| Application does not trust the imported CA | Imported into a different truststore than the one the application reads | Check the runtime configuration and the application's truststore path |

When troubleshooting, avoid deleting the keystore or generating a new key pair right away. First use `-list -v` to inspect the alias, entry type, chain, and validity period. If the certificate reply does not match the private key, generate a new CSR from the correct private-key entry and ask the CA to issue a matching certificate.

## 18. Recommended workflow

For a server TLS certificate, the typical workflow is:

1. Choose the keystore location and format, preferring PKCS12 for new projects.
2. Generate a key pair with `-genkeypair`, using a descriptive alias and a SAN matching the hostname.
3. Generate a CSR with `-certreq` from the exact alias.
4. Submit the CSR to the CA according to your organization's verification process.
5. Verify the CA certificate and fingerprint from a trusted source.
6. Import the appropriate certificate chain/trust anchor.
7. Import the certificate reply into the alias where the key pair was generated.
8. Use `-list -v` to confirm the `PrivateKeyEntry` and certificate chain.
9. Configure the server/application to point to the right keystore and alias.
10. Test TLS, hostname verification, the chain, and validity in the deployment environment.
11. Protect the private key, back up the keystore, and monitor certificate renewal schedules.

For a client that needs to trust a CA, create a dedicated truststore, import the verified CA certificate, and configure the application to use that truststore. Do not confuse a truststore containing trusted CAs with a keystore containing a server's private key.

## 19. Pre-deployment checklist

- [ ] Determined whether the purpose is storing a private key, a trusted certificate, or a secret key.
- [ ] Selected `PKCS12` or a format compatible with the target system.
- [ ] Alias is unique and accurately reflects the entry's purpose.
- [ ] Certificate has the appropriate subject, SAN, validity, and key usage.
- [ ] CSR was generated from the correct private-key entry.
- [ ] CA certificate and fingerprint were verified through an independent channel.
- [ ] Certificate reply matches the public key of the alias that generated the CSR.
- [ ] Certificate chain includes all required intermediates and trust anchors.
- [ ] `keytool -list -v` displays the expected entry type and chain.
- [ ] Application points to the correct keystore/truststore.
- [ ] Passwords are not hard-coded or recorded in shell history/logs.
- [ ] Private key is protected, keystore is backed up, and file permissions are properly restricted.
- [ ] Certificate has been tested against the actual hostname and environment.

`keytool` is the foundational tool for managing key pairs, certificates, and keystores in Java. Start by determining whether you need to hold a private key or trust another party's certificate; then choose the right keystore/truststore, alias, and format. For TLS, generate a key pair and CSR, verify the CA certificate before importing, import the certificate reply into the right alias, and re-verify the chain before deployment.

## References

- Oracle, The keytool Command, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html
- Oracle, Java Security Developer's Guide, JDK 17: https://docs.oracle.com/en/java/javase/17/security/java-security-overview1.html
