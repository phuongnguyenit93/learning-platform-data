# Checking Hostname Verification

## Objective

Hostname verification is the server identity check in a TLS connection. When a Spring Kafka application connects to a broker, the client must verify that the TLS certificate presented by the broker was actually issued for the hostname or IP address to which the client is connecting.

A secure TLS connection must pass two independent checks:

1. **Certificate chain verification:** the broker certificate is valid and signed by a CA the client trusts.
2. **Hostname verification (endpoint identity):** the server name the client uses must match an identifier in the broker certificate, usually in the Subject Alternative Name (SAN).

A valid truststore only proves the certificate belongs to a trusted CA. It does not prove the connected broker is the broker the application expects. Hostname verification adds this identity check and helps prevent TLS connections to an impostor server holding a certificate signed by a CA the client trusts.

In Kafka, this check occurs on the client side when establishing TLS to each broker. It applies when using SSL as well as SASL_SSL.

## Verification Flow When Spring Kafka Connects

When initiating a connection, the Kafka client reads hostnames from the bootstrap configuration. The client then receives cluster metadata containing broker addresses published via `advertised.listeners`. The client can open additional direct connections to those hostnames to send or receive data.

~~~mermaid
sequenceDiagram
    participant A as Spring Kafka client
    participant B as Kafka broker
    A->>B: Connect to hostname in bootstrap.servers
    B-->>A: Broker TLS certificate
    A->>A: Verify CA chain and hostname in SAN
    alt Both checks succeed
        A->>B: Complete TLS and exchange Kafka protocol
        B-->>A: Metadata containing advertised.listeners
        A->>B: Connect to brokers in metadata
    else Either check fails
        A-->>B: Abort TLS handshake
    end
~~~

Therefore, successfully connecting to a bootstrap server is not enough to conclude hostname configuration is right for the entire cluster. A broker may advertise a different hostname, or an individual broker's certificate may lack the matching SAN. Errors then commonly appear after the client receives metadata, when starting to produce, consume, or perform admin operations.

## Hostname Must Match the Certificate's SAN

Suppose the application is configured with:

~~~properties
spring.kafka.bootstrap-servers=broker-1.kafka.example.com:9093,broker-2.kafka.example.com:9093
~~~

The certificate returned by broker-1 needs a SAN matching `broker-1.kafka.example.com`; broker-2's certificate needs to cover `broker-2.kafka.example.com`. If clients connect via another DNS alias, that alias must also be included in the SAN of the corresponding certificate.

Example SAN section of broker-1's certificate:

~~~text
X509v3 Subject Alternative Name:
    DNS:broker-1.kafka.example.com
    DNS:kafka-bootstrap.example.com
    IP Address:10.20.0.11
~~~

Practical rules to remember:

- The client checks the hostname it actually uses to connect. The DNS name in config, the broker name advertised in metadata, and the name in the SAN must match.
- If the client connects by IP address, the certificate needs an IP Address SAN entry containing that exact address. A `DNS:10.20.0.11` entry does not substitute for an IP SAN.
- Ports are not included in SANs. SANs verify hostnames or IP addresses, not port numbers.
- Place DNS names in SANs. Do not rely on the legacy Common Name (CN) to replace SANs, as CN handling varies across TLS runtimes.
- Wildcards like `*.kafka.example.com` only match a single DNS label at the wildcard position; do not assume they cover multi-level names like `broker-1.zone.kafka.example.com`. Explicit per-broker SANs are usually easier to operate and audit.
- If using DNS aliases, load balancers, or TLS proxies, inspect the name the client sends to the endpoint and the actual certificate that endpoint returns. DNS resolving to the right IP does not automatically make the hostname in the certificate valid.

A cluster can use an individual certificate per broker or a certificate with multiple SANs. Either way, every hostname a client might connect to must be covered by the certificate presented by the corresponding endpoint.

## Checking `bootstrap.servers` and `advertised.listeners`

There are two hostname sources to inspect:

**Bootstrap servers** are the initial addresses in `spring.kafka.bootstrap-servers`. The client must verify the certificate of the endpoint each of these addresses reaches.

**Advertised listeners** are the broker addresses Kafka returns in metadata. Clients use them for subsequent connections. Advertised hostnames must:

- Be DNS-resolvable and reachable from the application's network.
- Match the SAN in the corresponding broker certificate.
- Use the right listener and port the client is allowed to access.
- Be consistent across environments, such as internal and external networks.

Example broker listener advertisement:

~~~properties
listeners=SSL://0.0.0.0:9093
advertised.listeners=SSL://broker-1.kafka.example.com:9093
listener.security.protocol.map=SSL:SSL
~~~

In this example, `0.0.0.0` is the bind address on the broker host; clients should not receive this bind address in metadata. Clients need to receive a reachable hostname such as `broker-1.kafka.example.com`, and the broker certificate must include that hostname in its SAN.

If the application bootstraps via `kafka-bootstrap.example.com` while metadata returns `broker-1.internal`, both names may need to appear in the SAN of the relevant endpoint certificates. The durable solution is usually configuring advertised listeners with hostnames clients can actually reach and issuing certificates matching those hostnames.

## Enabling Hostname Verification in Spring Boot

Kafka clients have the setting `ssl.endpoint.identification.algorithm`. The value `https` enables endpoint identification following TLS/HTTPS hostname verification rules. Even though the application speaks the Kafka protocol, the algorithm name is still `https`.

Starting with Kafka client version 2.0.0, the default value of this property is `https`. Older versions may have different defaults. Declaring it explicitly makes configuration and security intent easier to audit while avoiding reliance on library version defaults.

Example Spring Boot configuration with TLS:

~~~yaml
spring:
  kafka:
    bootstrap-servers:
      - broker-1.kafka.example.com:9093
      - broker-2.kafka.example.com:9093
    security:
      protocol: SSL
    ssl:
      trust-store-location: classpath:kafka-truststore.p12
      trust-store-password: <KAFKA_TRUSTSTORE_PASSWORD>
      trust-store-type: PKCS12
    properties:
      "[ssl.endpoint.identification.algorithm]": https
~~~

If using SASL over TLS, set `security.protocol` to `SASL_SSL` and configure the corresponding SASL mechanism. The hostname verification property keeps the value `https`.

In `application.properties`, it can be declared as:

~~~properties
spring.kafka.properties[ssl.endpoint.identification.algorithm]=https
~~~

Square-bracket syntax helps Spring Boot preserve Kafka property names containing multiple dots when binding into the `spring.kafka.properties` map.

If creating Kafka clients in Java or customizing factories, add the property to client config:

~~~java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.common.config.SslConfigs;

Map<String, Object> props = new HashMap<>();
props.put(
    SslConfigs.SSL_ENDPOINT_IDENTIFICATION_ALGORITHM_CONFIG,
    "https"
);
~~~

Ensure the property is applied to every client the application constructs manually, including producers, consumers, and AdminClient. If configuring Kafka Streams or custom factories separately, inspect those clients' configurations as well. Another client using different config can keep failing even after the main producer or consumer is fixed.

## Distinguishing Truststore, Keystore, and Hostname Verification

These three concepts answer different questions:

| Component | Role | Question Answered |
|---|---|---|
| Client truststore | Holds trusted CAs or certificates to verify the broker certificate | Do I trust the CA that issued this certificate? |
| Hostname verification | Matches the hostname the client connects to against the SAN in the broker certificate | Was this certificate issued for the exact server I intend to connect to? |
| Client keystore | Holds the client's certificate and private key, typically used in mutual TLS | Can the client prove its own identity to the broker? |

Hostname verification is the client's check of the **server's** identity. In mutual TLS, the broker also verifies the **client** certificate; verifying the client certificate does not replace the client's hostname verification of the broker.

When encountering a hostname mismatch error, adding a CA to the truststore usually will not fix the problem. Fix the connection hostname or reissue the certificate with the proper SAN.

## Inspecting Certificates and Endpoints

Run checks from a host or container sharing the same network path as the Spring Kafka application. Testing from an admin laptop may give different results if DNS, proxies, or listeners are split across networks.

### 1. Inspecting a certificate's SAN

If you have the PEM certificate file:

~~~bash
openssl x509 -in broker-1.crt -noout -subject -issuer -ext subjectAltName
~~~

Compare all DNS and IP entries against the hostnames or addresses used by clients. Inspect the broker's actual leaf certificate, not just the CA certificate in the truststore.

You can use keytool to inspect certificates:

~~~bash
keytool -printcert -file broker-1.crt
~~~

### 2. Testing TLS with the exact hostname

For a DNS endpoint:

~~~bash
openssl s_client \
  -connect broker-1.kafka.example.com:9093 \
  -servername broker-1.kafka.example.com \
  -verify_hostname broker-1.kafka.example.com \
  -verify_return_error \
  -CAfile ca.pem
~~~

For an endpoint called by clients via IP address:

~~~bash
openssl s_client \
  -connect 10.20.0.11:9093 \
  -verify_ip 10.20.0.11 \
  -verify_return_error \
  -CAfile ca.pem
~~~

The `-verify_hostname` and `-verify_ip` options verify endpoint identity; `-CAfile` supplies the CA used to verify the certificate chain. When the endpoint uses SNI or a proxy routing by SNI, `-servername` must carry the hostname the client expects to send.

Repeat the check for every broker and every hostname in configuration. A passing check against a bootstrap alias does not prove that all brokers in metadata have valid certificates.

### 3. Checking DNS and Kafka metadata

From the application's runtime environment, confirm the hostname resolves to the intended address and the broker port is reachable. Then inspect `advertised.listeners` on the Kafka side or the metadata received by the client. Cross-check every hostname returned by metadata against the SAN of the corresponding broker.

### 4. Enabling TLS debug logs when needed

If OpenSSL results differ from application errors, you can enable JVM TLS logs during a controlled reproduction:

~~~text
-Djavax.net.debug=ssl,handshake
~~~

Handshake logs can be very verbose and contain sensitive infrastructure details. Enable only temporarily, restrict where logs are stored, and turn off after collecting sufficient evidence. Do not post raw logs to public channels.

## Reading Common Errors

| Symptom | Common Meaning | Investigation Direction |
|---|---|---|
| `No subject alternative DNS name matching ... found` | The DNS hostname in use is absent from the certificate's SAN | Compare the hostname in the error with SAN; check bootstrap and advertised listener |
| `No name matching IP address ... found` | Client connected by IP, but the certificate lacks a matching IP SAN | Use a DNS hostname in the SAN or issue a certificate with the right IP SAN |
| `PKIX path building failed` | Client cannot build a certificate chain to a trusted CA | Check truststore, intermediate CAs, chain presented by broker, and certificate validity |
| Certificate expired or not yet valid | Certificate validity period is invalid | Check Not Before, Not After, and system clock synchronization |
| Bootstrap connects, but another node fails | Hostname or certificate of a broker in metadata mismatches | Check every address in advertised.listeners and every broker's certificate |
| `Connection to node ... could not be established` | Generic connection error; this message alone does not pinpoint TLS cause | Read root exception, hostname, and deeper causes in logs |

Do not conclude every `SSLHandshakeException` is a hostname mismatch. `PKIX path building failed` usually involves the trust chain; SAN errors indicate an endpoint identity mismatch. Distinguishing the two helps choose the exact fix.

## Procedure When Hostname Mismatch Occurs

When the application reports a hostname verification failure, proceed in this order:

1. **Extract the exact hostname from the error.** Note whether the application is connecting by DNS name or IP, which port, and which broker node.
2. **Identify the hostname source.** Check `spring.kafka.bootstrap-servers` first; if the error appears after receiving metadata, inspect hostnames in `advertised.listeners`.
3. **Inspect the actual endpoint certificate.** Retrieve the leaf certificate returned by the broker from the application's network and read its SAN.
4. **Check every broker.** Do not check only the first bootstrap node. Verify every hostname the client can receive from metadata.
5. **Fix configuration or certificates.** Prefer advertising stable DNS hostnames reachable by clients and issuing certificates whose SANs cover them. If multiple valid aliases exist, include every needed alias in the SAN.
6. **Re-verify with a TLS client and the application.** Re-run the OpenSSL check for every endpoint, then start or reconnect Spring Kafka and confirm producer, consumer, and AdminClient operate properly.
7. **Document the canonical configuration.** Record advertised hostnames, corresponding SANs, issuing CA, and certificate expiration so future renewals do not drop required hostnames.

If you need to rename `advertised.listeners`, confirm the new name resolves and is reachable from all client networks. Changing hostnames without updating DNS or certificates may simply shift the error to another connection phase.

## Why You Should Not Disable Hostname Verification

Endpoint identification can be disabled by setting the property to an empty string:

~~~properties
spring.kafka.properties[ssl.endpoint.identification.algorithm]=
~~~

This configuration skips matching the certificate's hostname. CA chain verification may still run, yet the client no longer checks whether the certificate belongs to the exact server it connected to. Another server holding a certificate issued by a trusted CA could pass chain validation despite not being the intended endpoint.

Consider this option only in an isolated test environment, time-bounded, with an explicit removal plan. Never use it as a production fix, never leave it in shared configuration, and never treat it as a solution for SAN errors. The proper fix is aligning connection hostnames, advertised listeners, and certificate SANs.

## Operational Checklist

Before promoting a Kafka client to production or after changing DNS, listeners, or certificates, verify:

- [ ] Kafka clients have `ssl.endpoint.identification.algorithm=https`.
- [ ] Every hostname in `bootstrap.servers` is present in the corresponding endpoint's SAN.
- [ ] Every hostname returned via `advertised.listeners` is reachable from the application network and matches the SAN.
- [ ] If clients use IPs, certificates include the exact IP Address SAN.
- [ ] Certificates are within validity and the CA chain is trusted by the client truststore.
- [ ] Producer, consumer, AdminClient, and custom clients share the same hostname verification policy.
- [ ] TLS checks are executed from a network environment close to the application.
- [ ] No production configuration sets `ssl.endpoint.identification.algorithm` to an empty string.

Hostname verification lets the client confirm the broker it speaks with is truly the endpoint identified in the certificate. Stable operations require keeping three places aligned: the hostname the client uses, the hostname Kafka advertises, and the SAN of the broker certificate.
