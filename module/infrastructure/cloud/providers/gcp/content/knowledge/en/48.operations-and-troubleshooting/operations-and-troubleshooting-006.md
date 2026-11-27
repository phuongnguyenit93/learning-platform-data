# Troubleshooting Load Balancer Certificate, DNS, and Health Check Errors

A Java/Spring Boot application may run fine in a container or VM, yet users accessing it via a domain encounter **ERR_CERT_COMMON_NAME_INVALID**, **DNS_PROBE_FINISHED_NXDOMAIN**, **502 Bad Gateway**, or **503 Service Unavailable**. These symptoms can stem from very different layers: DNS returning an old IP, the load balancer serving the wrong certificate, a target proxy picking the wrong config, a firewall blocking health checks, or the application returning an unsuitable HTTP status on the health check path. Restarting Pods or changing DNS immediately on error can prolong the outage and widen the blast radius.

Within the **Operations and Troubleshooting** chapter of the **CLOUD_PROVIDERS_GCP** module, this lesson builds an ordered diagnostic workflow for Google Cloud Load Balancing, Cloud DNS, Certificate Manager, Compute Engine, GKE, Cloud Run, and related backends. The emphasis is on observing and isolating the fault first, distinguishing behavior across load balancer types, applying safe changes, and verifying recovery with concrete evidence.

After this lesson, learners will be able to:

- Trace the path of an HTTP(S) request from DNS to frontend, TLS proxy, URL map, backend service, and application.
- Classify DNS, TLS/certificate, routing, and backend health errors from client symptoms.
- Diagnose Google-managed and self-managed certificates, Certificate Manager, DNS authorization, CAA, SNI, and certificate chains.
- Distinguish health checks for Application/Network Load Balancers, GKE Ingress, and serverless NEGs.
- Verify health-check probe IP ranges, firewalls, ports, request paths, host headers, response codes, timeouts, and thresholds.
- Use `dig`, `nslookup`, `curl`, `openssl`, `gcloud`, Logs Explorer, and Cloud Monitoring.
- Build runbooks for failures after DNS changes, certificate rotations, application rollouts, or firewall edits.
- Design pre-cutover tests, certificate expiration alerts, unhealthy-backend alerts, and rollback plans.

## 1. The Big Picture: Which Layers Does a Request Traverse?

For an **external Application Load Balancer** terminating TLS at the frontend, the typical path is:

~~~mermaid
flowchart LR
    U[User] --> DNS[DNS resolver A/AAAA]
    DNS --> VIP[Frontend IP + forwarding rule]
    VIP --> TLS[Target HTTPS proxy + certificate]
    TLS --> Route[URL map / host-path rules]
    Route --> BS[Backend service]
    BS --> BE[Instance group / NEG]
    BE --> APP[Java / Spring API]
    HC[Health-check probers] -.Probes supported backends.-> BE
    BE --> DB[(Cloud SQL / dependent services)]
~~~

Every point in the diagram has its own failure modes and evidence. An error occurring before TLS completes **will not generate backend HTTP request logs**. A 404 may come from the URL map or from Spring Boot itself. A backend marked healthy does not prove every business endpoint succeeds.

With a **proxy Network Load Balancer**, the routing flow differs: there is usually no host/path URL map like an Application Load Balancer. With a **passthrough Network Load Balancer**, connections and health checks differ as well. Therefore, the first step is always identifying **the exact load balancer and backend type** rather than applying a global external Application Load Balancer checklist everywhere.

### 1.1. Component Groups

| Component | Primary Job | Typical Failures |
|---|---|---|
| Authoritative/recursive DNS | Resolves hostname to IPv4/IPv6 addresses | NXDOMAIN, SERVFAIL, wrong A/AAAA, stale cache |
| Forwarding rule/VIP | Accepts connections on configured IP and port | Wrong IP, wrong port, missing rule |
| TLS target proxy | Selects certificate via SNI, enforces SSL policy | Wrong cert name, expired, missing chain, handshake failed |
| URL map | Routes to backend by hostname/path | 404, wrong backend selected, redirect loop |
| Backend service | Distributes requests to eligible backends | No healthy backends, misconfigured timeout |
| Health check | Determines whether a backend can serve traffic | Failing port/path/host/firewall/response code |
| Application backend | Processes actual requests | 500, timeouts, exhausted database connections |
| Network/IAM | Permits the required connectivity path | Firewall deny, Private Service Connect/NEG mismatch |

### 1.2. Three Error Types to Separate

1. **Hostname does not resolve:** stop at DNS; do not touch certificates or Pods yet.
2. **Resolves, yet TLS handshake fails:** inspect target IP, SNI, certificate resource/attachment, chain, policy, and TLS version.
3. **TLS succeeds, yet HTTP returns 4xx/5xx:** inspect URL map, backend health, and logs; do not assume a certificate error.

Ask: does the error affect **the entire domain**, **one hostname**, **one path**, **one region**, **one client type**, or **a subset of requests**? Narrowing scope identifies the suspect layer far faster than random tweaks.

## 2. Gathering Context Before Touching Production

Open an incident per internal process if the error budget or business SLO is impacted. Collect:

- Project ID, region/zone, load balancer name, load balancer type, and frontend IP name.
- Domain/FQDN, UTC timestamp, client IP/ASN, or affected geography.
- HTTP/HTTPS port, IPv4/IPv6 protocol, SNI hostname.
- Frontend forwarding rule, target proxy, URL map, backend service, NEG/instance group.
- Attached Certificate Manager certificate/map or Compute Engine SSL certificate.
- Health-check type, port, path, host, thresholds, timeout, and logging config.
- Recent changes: DNS, ingress, SSL policy, certificate rotation, GKE rollout, firewall, IAM, migrations.
- Verbatim error message, HTTP status, request ID, trace, LB logs, and backend logs.

Never paste tokens, private keys, session cookies, or customer data into tickets or debug channels. When sharing `openssl` output, include only public certificate chain metadata, issuer, SAN, expiry, and verification status; **never share private keys**.

### 2.1. Non-Destructive Investigation Commands

~~~bash
# Read-only inspection. Replace placeholders before running.
gcloud config get-value project
gcloud compute forwarding-rules list
gcloud compute backend-services list
gcloud compute health-checks list
gcloud certificate-manager certificates list
gcloud compute ssl-certificates list --global
~~~

Regional resources require `--region=REGION` on supporting commands, whereas global resources use `--global`. Do not assume the backend service name matches the Kubernetes or Cloud Run service name. In Shared VPC or multi-project topologies, verify which projects own the forwarding rule, backends, and certificates.

### 2.2. Never Change Multiple Layers at Once

If you simultaneously update an A record, rotate a certificate, edit a URL map, change a firewall, and deploy a new revision, it becomes impossible to know which change fixed the problem. Each step needs:

1. A concrete hypothesis.
2. A non-destructive test confirming or refuting it.
3. The smallest possible fix.
4. Application timestamp and expected propagation delay.
5. Rollback steps and recovery metrics.

## 3. Quick Symptom-Based Triage Table

| Client Symptom | Priority Layer to Check | Useful Evidence |
|---|---|---|
| `NXDOMAIN` | Authoritative DNS/delegation, record name | `dig +trace`, SOA, NS |
| `SERVFAIL` | DNSSEC, resolver/authoritative, policy | `dig +dnssec`, check DS/DNSKEY |
| DNS returns old IP | A/AAAA, resolver cache, TTL, delegation | `dig @authoritative` and public resolvers |
| IPv4 clients work yet IPv6 fails | AAAA and frontend IPv6 | `curl -4`, `curl -6`, forwarding rule |
| `ERR_CERT_COMMON_NAME_INVALID` | SNI, SAN, LB IP, certificate map | `openssl s_client -servername` |
| Expired certificate | Rotation/renewal/cert attachment | `notAfter`, managed status, and CA authorization |
| `SSL handshake failure` | TLS version/cipher, cert chain, SNI | `openssl s_client`, SSL policy |
| HTTPS 301/302 loop | URL map, redirects, backend proxy headers | `curl -IL` and app config |
| HTTPS 404 | URL map host/path or application | LB `statusDetails` and backend logs |
| HTTPS 502/503 | Backend health/connection/timeout or LB config | LB logs, `backend-services get-health`, health-check logging |
| Backend `UNHEALTHY` | Port/path/host/status/threshold/firewall | `get-health`, health-check describe, app logs |
| GKE Ingress healthy yet requests fail | Readiness vs business endpoint, NEG, rollout | GKE events, Service/EndpointSlice, logs |
| Cloud Run serverless NEG errors | Service/revision/ingress/auth/cold start | Cloud Run metrics/logs; do not look for non-existent LB health checks |

This table is **directional**, not a one-to-one rule. A 503 can be returned by the application itself or by the load balancer failing to pick a backend; separate them via request logs and `statusDetails`.

## 4. DNS: From Registrar to Frontend IP

### 4.1. Resolution Chain

For `api.example.com`:

~~~mermaid
flowchart LR
    C[Client] --> R[Recursive resolver]
    R --> Root[Root DNS]
    Root --> TLD[.com nameservers]
    TLD --> NS[Authoritative NS for example.com]
    NS --> RR[A / AAAA / CNAME record]
    RR --> IP[Load balancer VIP]
~~~

Recursive resolvers usually cache intermediate steps rather than walking the whole chain on every request. Updating a record in Cloud DNS **is not enough** if the registrar still delegates the domain to a different DNS provider. Moreover, public and private zones with the same name can return different answers depending on environment.

### 4.2. Layered DNS Diagnostics

~~~bash
# Check records from the default resolver.
dig api.example.com A
dig api.example.com AAAA
dig api.example.com CNAME

# Compare public resolvers.
dig @8.8.8.8 api.example.com A
dig @1.1.1.1 api.example.com A

# Inspect authoritative nameservers and delegation path.
dig example.com NS
dig +trace api.example.com A

# Check SOA and TTL.
dig example.com SOA
dig api.example.com A +noall +answer
~~~

Record both `ANSWER SECTION`, `AUTHORITY SECTION`, status, and TTL. Returning a record that points to **the wrong forwarding rule IP** is still a failure; do not check only "whether an IP came back."

### 4.3. Cloud DNS

~~~bash
gcloud dns managed-zones list --project=DNS_PROJECT_ID

gcloud dns managed-zones describe ZONE_NAME \
  --project=DNS_PROJECT_ID

gcloud dns record-sets list \
  --zone=ZONE_NAME \
  --project=DNS_PROJECT_ID
~~~

Cloud DNS zones can be public or private; private zones have VPC-level visibility. Records in a private zone are not exposed to public Certificate Authorities on the Internet. When a certificate requires DNS authorization, the verification record must live in the domain's **public authoritative DNS** per the chosen mechanism.

### 4.4. TTL and Negative Caching

- A/AAAA/CNAME TTLs indicate how long resolvers may cache records, though applications and OS networks may maintain separate caches.
- Lower TTLs well ahead of cutover for migrating records so stale caches expire quickly.
- `NXDOMAIN` responses can be **negatively cached** per SOA settings, so adding a new record may not take effect immediately across all resolvers.
- Some resolvers/clients ignore exact TTLs; never promise instantaneous cutovers.
- When verifying a new VIP immediately, use `curl --resolve` to bypass DNS for that test alone.

Do not delete old A/AAAA records until you confirm cutover reached all client cohorts and certificates are ready. A DNS rollback does not automatically reconcile transaction or database state.

### 4.5. IPv6 and Dual Stack

A correct A record alongside an AAAA record pointing to an IPv6 address not served by the LB can break IPv6 clients. Test both:

~~~bash
curl -4 -vI https://api.example.com/health
curl -6 -vI https://api.example.com/health
dig api.example.com A +short
dig api.example.com AAAA +short
~~~

If the LB lacks an IPv6 frontend, do not leave a stale AAAA record pointing to another service. If removing AAAA records, perform a controlled change since IPv6-only clients may be affected.

### 4.6. DNSSEC and SERVFAIL

If authoritative DNS moved providers, check DS records at the registrar and DNSKEY records in the DNS zone. Stale DS records can make validating resolvers return `SERVFAIL` even when authoritative servers answer A/AAAA normally. Use:

~~~bash
dig +dnssec api.example.com A
dig example.com DS
dig example.com DNSKEY
~~~

Never disable DNSSEC wholesale as a "quick test" in production. Reconcile the delegation/signing chain and DNS provider migration runbook.

## 5. TLS Certificates: Distinguishing GCP Resource Types

On Google Cloud, two main certificate families are common:

1. **Compute Engine SSL certificates** (Classic Certificates), including Google-managed and self-managed, managed via `gcloud compute ssl-certificates`. Support varies by load balancer; not all regional LBs support this Google-managed type.
2. **Certificate Manager certificates**, including Google-managed (with load balancer authorization or DNS authorization) and self-managed. Managed via `gcloud certificate-manager`, certificate maps, or direct attachment to target proxies depending on LB type.

A certificate showing **ACTIVE** only means issuance succeeded; it does not prove the load balancer is serving it. Verify **certificate map/entry, hostname selector, target proxy attachment, propagation, and the client-observed chain**.

### 5.1. Scope Differences

| Component | Global | Regional |
|---|---|---|
| Compute Engine Google-managed SSL certificate | Used for supported global LB types | Not generally applicable to regional Application LB |
| Certificate Manager Google-managed | Global certificates; DNS auth or LB auth by type | Regional certificates; requires matching DNS authorization |
| Certificate map | Used with supported global configs | Attachment differs; regional often attaches directly to target proxy |
| Target HTTPS proxy | Exists in global and regional forms | `gcloud` commands require matching scope |

For **regional Google-managed Certificate Manager certificates**, you must use a **regional, per-project DNS authorization** scoped to the same region. Do not create a global DNS authorization and expect to attach it to a regional certificate.

### 5.2. Inspecting Compute Engine Managed Certificates

~~~bash
gcloud compute ssl-certificates list --global

gcloud compute ssl-certificates describe CERT_NAME \
  --global \
  --format="yaml(name,type,managed.status,managed.domainStatus,expireTime)"
~~~

Notable statuses:

- `PROVISIONING`: verifying/issuing certificate; check DNS, LB attachment, and propagation time.
- `ACTIVE`: issued; verify whether it is actually being served.
- `FAILED_NOT_VISIBLE` on a domain: CA cannot reach the domain via the expected load balancer IP.
- `FAILED_CAA_CHECKING` or `FAILED_CAA_FORBIDDEN`: check the CAA chain and permitted CAs.
- `FAILED_RATE_LIMITED`: CA rate-limited issuance; stop repeatedly creating new certificates.

These status names belong to **Compute Engine SSL certificates**. Do not treat them as universal enums for every Certificate Manager resource.

### 5.3. Inspecting Certificate Manager Certificates

~~~bash
gcloud certificate-manager certificates list --location=global

gcloud certificate-manager certificates describe CERT_NAME \
  --location=global \
  --format="yaml(name,managed.state,managed.provisioningIssue,managed.authorizationAttemptInfo,sanDnsnames,expireTime)"

gcloud certificate-manager dns-authorizations list --location=global
~~~

For regional certificates, replace `--location=global` with the actual region. Key fields:

- `managed.state=PROVISIONING`: issuance/renewal in progress; inspect `provisioningIssue` and `authorizationAttemptInfo`.
- `managed.state=ACTIVE`: certificate is ready, though it must still be attached to the right proxy/map.
- `managed.state=FAILED`: issuance/renewal failed; fix the root cause and follow guidance for replacement resources rather than assuming infinite automatic retries.
- `authorizationAttemptInfo.failureReason`: may be `CONFIG`, `CAA`, or `RATE_LIMITED`.

Depending on certificate variant and rollout state, `describe` output fields may vary. Rely on actual API output rather than assuming every field is always populated.

## 6. Google-Managed Certificate Fails to Issue or Renew

### 6.1. Load Balancer Authorization

With **load balancer authorization**, the CA verifies that the domain points to a valid LB frontend. Check:

- A and AAAA records for **all SAN domains** point to the exact frontend IPs, with no leftover old IPs or stray IPv6 addresses.
- Target proxy and forwarding rule exist and serve port 443.
- Certificate config is valid and attached to the target proxy per product documentation.
- Authoritative DNS returns consistent answers from multiple networks/locations.
- External CDNs, GeoDNS, or reverse proxies may interfere with multi-perspective domain validation (MPIC).
- CAA records permit the CA used by Google-managed certificates.

For Google-managed Compute Engine certificates, provisioning can take up to roughly **60 minutes after DNS/LB changes propagate**, and DNS propagation itself can take longer depending on resolvers. Never churn certificates repeatedly while config is broken, as rate limits and backoffs prolong the delay.

### 6.2. DNS Authorization

Certificate Manager offers **DNS authorization** to prove domain control via an API-generated CNAME record. This works even before public DNS points to the LB frontend or when a CDN sits in front.

~~~bash
gcloud certificate-manager dns-authorizations describe AUTH_NAME \
  --location=global
~~~

Read `dnsResourceRecord.name`, `type`, and `data` from the output. Create the **exact CNAME** in authoritative public DNS; never guess the record name from the domain. Verify with:

~~~bash
dig _acme-challenge.example.com CNAME +short
~~~

With `PER_PROJECT_RECORD`, the CNAME includes a project-specific suffix and is **not necessarily** literally `_acme-challenge.example.com`; copy it verbatim from `dnsResourceRecord`. Never create both a CNAME and a TXT record at the same owner name, as DNS standards prohibit CNAMEs coexisting with other RR types.

Google-managed regional Certificate Manager certificates use **per-project regional DNS authorization**. If the CNAME is configured yet `managed.state` stays `PROVISIONING`, inspect authorization attempts and check what authoritative public DNS is actually returning.

### 6.3. CAA Records

CAA records let domain owners restrict which CAs can issue certificates. Inspect:

~~~bash
dig example.com CAA
dig api.example.com CAA
~~~

For **per-project DNS authorization** (including regional managed certificates), the supported CA is **Google Trust Services**, so CAA must allow `pki.goog`. For other mechanisms, Google may use `pki.goog` or `letsencrypt.org` per certificate type documentation. Parent-domain CAA records can also apply to subdomains per DNS/CAA rules.

Only modify records with domain owner approval; never strip all CAA restrictions across the entire domain to unblock a single certificate.

### 6.4. GeoDNS, CDN, and MPIC

In GeoDNS setups, `api.example.com` resolves to different IPs by location. Certificate Authorities validate from **multiple vantage points**; a single location returning the wrong IP can break issuance or renewal.

If a third-party CDN sits in front of the LB, load balancer authorization checks may never reach the LB. In that case, consider **Certificate Manager DNS authorization** rather than disabling the CDN or exposing the origin unprotected. Any change must align with system architecture and security policy.

## 7. Certificate Is ACTIVE Yet Clients Still Receive the Wrong Cert

`ACTIVE` does not guarantee the frontend is serving that certificate. Check:

1. Do the FQDN/SANs match the client's hostname, including wildcard rules?
2. Is the client resolving to the right forwarding rule IP?
3. Does the target HTTPS proxy reference a **Certificate Manager map** or a **Compute SSL certificate directly**?
4. Inside the certificate map, does the exact/wildcard/default hostname entry point to the expected certificate?
5. Does each target proxy (global/regional) match the right scope and certificate resource?
6. Have attachment and propagation to GFE finished?
7. Does the client send **SNI**? Without SNI, it may receive the default certificate.

### 7.1. Testing from the Client with SNI

~~~bash
# Observe the chain actually served by the LB; no private key needed.
echo | openssl s_client \
  -connect LB_IP:443 \
  -servername api.example.com \
  -showcerts \
  -verify_return_error

# Inspect the leaf certificate.
echo | openssl s_client -connect LB_IP:443 \
  -servername api.example.com 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates -ext subjectAltName
~~~

If clients connect by hostname with SNI yet your `openssl` check omits `-servername`, you may receive the **default certificate** and draw the wrong conclusion. `CN` alone is insufficient; verify **SANs**, chain, and CA trust. For example, wildcard `*.example.com` covers neither the apex `example.com` nor two-level subdomains like `a.b.example.com`.

### 7.2. Inspecting Target HTTPS Proxies and Maps

~~~bash
gcloud compute target-https-proxies list
gcloud compute target-https-proxies describe PROXY_NAME --global

gcloud certificate-manager maps list
gcloud certificate-manager maps entries list --map=MAP_NAME
gcloud certificate-manager maps entries describe ENTRY_NAME --map=MAP_NAME
~~~

For regional proxies, pass `--region=REGION` if the resource belongs to a regional LB; for regional Certificate Manager resources, check supported direct attachment methods. Directly attached proxy certificates and certificate maps follow specific precedence rules; when a certificate map is attached to a proxy, **do not assume** a directly attached certificate will still be selected.

### 7.3. Self-Managed Certificates

Check:

- Leaf certificate, intermediate chain, issuer, and expiration.
- That the uploaded private key matches the public certificate (verify safely on authorized systems only; never expose keys).
- PEM chain ordering without missing intermediates.
- Complete SAN coverage and valid attachment path.
- SSL policy supports TLS versions/ciphers required by clients.
- Certificate rotation follows **attach new → verify → remove old**.

Never delete the old certificate immediately after uploading a new one. Verify propagation, remaining IPv4/IPv6 clients, and the live certificate served across all frontends.

### 7.4. TLS Version, Ciphers, and mTLS

Handshake failures are not always certificate issues. Check:

- SSL policy minimum TLS 1.2/1.3 alignment with system and client requirements.
- Whether legacy devices/clients support the configured ciphers/key algorithms.
- If **mTLS** is required, how trust stores/client CA verification between clients and the LB are configured.
- Never downgrade an SSL policy to obsolete TLS versions for a legacy client without security approval.

Frontend TLS (user to LB) and backend TLS (LB to **HTTPS backend**) are two separate connections. A valid frontend certificate does not prove backend TLS is working. Inspect the failing side.

## 8. Testing DNS Independently from Certificates

`curl --resolve` pins a hostname to a specific IP for a single test while **preserving SNI and the `Host` header**:

~~~bash
curl -vk --resolve api.example.com:443:LB_IP \
  https://api.example.com/health
~~~

**Diagnostic outcomes:**

- If hostname access fails yet `--resolve` to the right `LB_IP` succeeds: focus on DNS/caching/delegation.
- If both show the exact same cert error: inspect the cert served by `LB_IP`, SNI, and cert maps.
- If TLS succeeds yet HTTP returns 503: move to backend/health checks—do not touch DNS.
- If hitting `https://LB_IP` directly fails hostname validation: that is expected behavior for domain-issued certificates, not a misconfiguration.

`-k` skips certificate verification and is for debugging only; **never use it as proof of valid TLS security**. For final verification, omit `-k`:

~~~bash
curl -v --resolve api.example.com:443:LB_IP \
  https://api.example.com/health
~~~

## 9. Health Checks: What Is the Load Balancer Actually Measuring?

A health check is a probe from Google infrastructure (or a proxy tier depending on LB type) to a backend to decide whether that backend is eligible for traffic. It does not automatically test end-to-end business journeys and does not necessarily hit the same port or path users call.

### 9.1. Common Health Check Types

| Health Check Type | What It Checks | Common Failures |
|---|---|---|
| TCP | Whether a TCP connection succeeds on IP:port | No listener, firewall deny, wrong port |
| HTTP | Sends an HTTP request to host/path/port | 301/302, 401, 404, 500, host mismatch |
| HTTPS | TLS + HTTP request to backend | Backend TLS/cert mismatch, port/path, app error |
| HTTP/2 | HTTP/2 protocol request if supported by backend | Protocol mismatch, timeout |
| SSL | SSL/TLS handshake per supported LB/backend | Misconfigured TLS |
| gRPC | gRPC Health Checking Protocol status | Health service/method not implemented |

Supported health check types depend on the LB/backend and backend service. Do not choose an HTTPS health check just because users call an HTTPS frontend: the LB can terminate TLS at the frontend and talk HTTP to backends. Check the actual backend configuration.

### 9.2. Healthy/Unhealthy State Transitions

Health checkers use thresholds:

- `checkIntervalSec`: interval between probes.
- `timeoutSec`: deadline for a single probe.
- `healthyThreshold`: consecutive successes required to become Healthy.
- `unhealthyThreshold`: consecutive failures required to become Unhealthy.

Probes can originate from multiple sources; transition time is not simply a single multiplication. After fixing a firewall or application, wait sufficient cycles and inspect status/health logs instead of frantically refreshing the Console.

### 9.3. Health Checks Need a Clear Contract

With Spring Boot Actuator:

- `/actuator/health/liveness`: does the process need a restart?
- `/actuator/health/readiness`: is the instance ready to receive traffic?

You do not necessarily use liveness or readiness verbatim as the **Google LB health check** in every environment. Design the probed path around fault tolerance:

- Return success only when the instance can genuinely serve user requests.
- Do not require authentication on the probe path if probers do not send credentials; restrict access at the network layer.
- Avoid unintended HTTP-to-HTTPS redirects when the backend probe uses HTTP.
- Return HTTP 200 per health-check expectations; depending on service, 301/302 redirects or 204 may count as failures—check exact health-check expectations.
- Avoid checking non-essential external dependencies in a way that marks every instance unhealthy when one auxiliary service blips.

## 10. Health-Check Probe Sources and Firewalls

**There is no single health-check IP range shared by all LBs and backends.** Consult Google Cloud's *Probe IP ranges and firewall rules* table for your exact Application/Network LB type, scope, backend type, and IPv4/IPv6 setup.

### 10.1. Key Differences

| LB/Backend | Health-Check Probe Source | Important Note |
|---|---|---|
| Global external Application LB + VM instance group/zonal NEG | Google health-check system IP ranges | Check current source table, e.g., `35.191.0.0/16` for documented configs |
| Regional external/internal Application LB + VM/zonal NEG | Google health-check IP ranges per LB type | **Proxy-only subnet** is the Envoy data-plane traffic source, distinct from health-check probes |
| Hybrid NEG or regional internet NEG | May originate from the Envoy proxy-only subnet per product | Firewalls/routes must match the actual sender |
| External/internal passthrough Network LB | Product- and IPv4/IPv6-specific ranges | Some configs differ from Application LB sources |
| Serverless NEG (Cloud Run) | **No LB-level health check supported** | Check Cloud Run service/revision/app health and ingress |
| Private Service Connect NEG | Does not use VM-style health-check resources | Check PSC/producer/service status |

Older tutorials often cite `35.191.0.0/16` and `130.211.0.0/22`; **never allow only those two ranges unconditionally** or ignore other current ranges such as IPv6 or passthrough LBs. Use the exact documented ranges for your specific LB.

### 10.2. Firewalls for Backend VMs

Example allow-rule syntax (apply only after verifying probe sources):

~~~bash
gcloud compute firewall-rules create allow-selected-hc \
  --network=VPC_NAME \
  --direction=INGRESS \
  --priority=1000 \
  --action=ALLOW \
  --rules=tcp:8080 \
  --source-ranges=VERIFIED_PROBE_CIDR \
  --target-tags=allow-app-hc
~~~

`VERIFIED_PROBE_CIDR` is a **placeholder**—do not run it literally. The rule needs the exact VPC, target (network tag or service account), backend port, and scope. Organization/folder/VPC firewall policies and guest OS firewalls/`iptables` can still deny traffic. Avoid opening `0.0.0.0/0` to application ports just to make health checks pass.

### 10.3. Proxy-Only Subnet Is Not the Health-Check Subnet

Envoy-based regional internal/external Application Load Balancers require a **proxy-only subnet**. Frontend-to-backend traffic originates from the proxy-only subnet, whereas probes to VMs/zonal NEGs may come from separate health-check ranges. A backend can show Healthy while real user requests are blocked by a firewall missing rules for the proxy-only subnet.

Verification must cover **both paths**:

1. Health checker → backend: do probes reach the right port?
2. Envoy proxy → backend: do firewalls/networks permit application traffic?

Never treat `get-health HEALTHY` as proof that all network data flows are permitted.

## 11. Reading Backend Config and Health via gcloud

### 11.1. Identify the Attached Health Check

~~~bash
gcloud compute backend-services describe BACKEND_SERVICE \
  --global \
  --format="yaml(name,protocol,portName,healthChecks,backends,timeoutSec,logConfig)"

gcloud compute health-checks describe HEALTH_CHECK \
  --global
~~~

For regional backends, replace `--global` with `--region=REGION`. For legacy health checks or Network LBs using different configs, inspect the exact resource type instead of forcing global commands.

Verify:

- Which health check is the backend service referencing?
- Is the health-check port fixed or `USE_SERVING_PORT`?
- Does the instance group define a **named port** matching the backend service's `portName`?
- For zonal NEGs, are endpoint IPs/ports accurate and listening?
- Do timeout and request path match the application contract?

### 11.2. Read Backend Health

~~~bash
gcloud compute backend-services get-health BACKEND_SERVICE --global

# Regional backend:
gcloud compute backend-services get-health BACKEND_SERVICE \
  --region=REGION
~~~

Results identify which backend instances/groups are Healthy/Unhealthy and the scope of impact. If all backends turn Unhealthy right after a firewall edit, inspect firewalls before restarting apps. If only one instance is Unhealthy, inspect that node's instance logs, process, port, and resources.

### 11.3. Inspecting Directly Inside the VM

Example on a Linux VM serving port 8080:

~~~bash
ss -lntp | grep ':8080'
curl -v --max-time 5 http://127.0.0.1:8080/healthz

# Test via internal IP only when network and IAM permit.
curl -v --max-time 5 http://BACKEND_PRIVATE_IP:8080/healthz
~~~

Loopback success does not prove the app binds `0.0.0.0` or the backend NIC IP, nor does it prove Google probes pass firewalls. Combine listener checks, host firewalls, VPC firewalls, health-check logs, and `get-health`.

## 12. Health Check Wrong Path, Port, Host, or Status Code

### 12.1. Port Mismatch

Common scenarios:

- Health check probes port 80 while the app listens on 8080.
- Backend service `portName` is `http`, yet the instance group lacks a matching named port mapping.
- NEG endpoint IP:port from a Pod differs from the actual container port.
- Kubernetes Service `port`, `targetPort`, and `nodePort` are mixed up.

Check all 4 layers: health check → backend service → instance group/NEG → application listener. For instance groups, verify named ports:

~~~bash
gcloud compute instance-groups managed get-named-ports MIG_NAME \
  --zone=ZONE
~~~

This applies to zonal MIGs; regional MIGs use corresponding flags. Never assume the backend port always derives from the health-check port.

### 12.2. Path Mismatch

For example, the health check requests `GET /` while Spring Boot only serves `/actuator/health`. If `/` returns 404, backends are marked unhealthy even though the main API works.

Test the path with `curl` from an authorized environment:

~~~bash
curl -i http://BACKEND_PRIVATE_IP:8080/
curl -i http://BACKEND_PRIVATE_IP:8080/actuator/health/readiness
~~~

Update the health-check request path to a stable application-maintained endpoint; never add an arbitrary dummy route that always returns 200 regardless of serving health.

### 12.3. Host Header and Virtual Hosts

A backend may route by hostname, such as `Host: api.internal.example.com`. By default, health checks send a `Host` header determined by the check type, which may differ from the external domain. When the app/web server only returns 200 for a configured virtual host, probes get 404.

Test:

~~~bash
curl -i \
  -H 'Host: api.internal.example.com' \
  http://BACKEND_PRIVATE_IP:8080/healthz
~~~

Set the health check's `host` field as needed if supported by the probe type. Never use the public domain as the `Host` for internal backends without checking redirects, HSTS, and host validation.

### 12.4. Authentication and Redirects

If Spring Security protects `/actuator/health` with login/OAuth, health checkers lack bearer tokens and receive 401/403. Expose a dedicated minimal health endpoint restricted at the network layer without leaking sensitive info.

If an HTTP backend redirects to HTTPS with 301/302 while the HTTP health checker expects 200, backends may be marked unhealthy. Choose the matching probe protocol or exclude `/healthz` from redirects safely. Never disable TLS everywhere just to pass health checks.

### 12.5. Overly Strict Readiness

If readiness calls every external dependency (email, analytics, third-party APIs), a minor blip can make every instance return 503, wiping out all LB healthy capacity. Include only dependencies **truly required to accept requests** in readiness; keep liveness simple to prevent restart storms.

## 13. GKE: Ingress, Service, Pod Readiness, and NEGs

GKE offers multiple ways to expose applications: Ingress/Gateway with Application Load Balancers, `Service` type `LoadBalancer` (passthrough Network LB), standalone NEGs, and service meshes. They do **not** share the same health-check mechanics.

### 13.1. With GKE Ingress

Inspect:

~~~bash
kubectl get ingress -A
kubectl describe ingress INGRESS_NAME -n NAMESPACE
kubectl get services -n NAMESPACE
kubectl describe service SERVICE_NAME -n NAMESPACE
kubectl get pods -n NAMESPACE -o wide
kubectl get endpointslices -n NAMESPACE
kubectl describe pod POD_NAME -n NAMESPACE
~~~

In Cloud Console → Load Balancing, inspect the backend service and health check created by the GKE controller and check `get-health`. A Pod showing `Ready=True` does not guarantee the Google Load Balancer health check is configured properly and reporting Healthy.

### 13.2. BackendConfig, `readinessProbe`, and Health Check Inference

With GKE Ingress, health check settings may come from a **BackendConfig** or be inferred from Pod readiness probes when the backend is first created. Updating `readinessProbe` in a Deployment later **does not necessarily update the existing LB health-check resource**. For deterministic configuration, use `BackendConfig` per GKE documentation.

Abbreviated `BackendConfig` example for GKE Ingress:

~~~yaml
apiVersion: cloud.google.com/v1
kind: BackendConfig
metadata:
  name: api-hc
spec:
  healthCheck:
    type: HTTP
    requestPath: /actuator/health/readiness
    port: 8080
    checkIntervalSec: 10
    timeoutSec: 5
    healthyThreshold: 2
    unhealthyThreshold: 3
~~~

Attach the `BackendConfig` via annotations on the exact Kubernetes Service port. The port in `BackendConfig` must match the backend mode (container-native NEG vs. instance group). This is a structural example; verify against your exact GKE version and LB type before applying.

### 13.3. Pods and Networking

- A Pod may report `Ready=True` while the app binds only `localhost`, refusing connections to the Pod IP.
- A mismatched Service selector omits serving Pods from `EndpointSlice`.
- NEG endpoints have not finished syncing after a rollout.
- NetworkPolicies, VPC firewalls, or mesh policies block probes.
- Slow startup causes health checkers to mark backends unhealthy before the app finishes booting.
- Rolling updates may temporarily leave too few healthy replicas if surge/unavailable settings, HPA, or PodDisruptionBudgets are misconfigured.

### 13.4. Service Type LoadBalancer

GKE `Service(type=LoadBalancer)` normally uses a passthrough Network LB; health checks may target `nodePort` and depend on `externalTrafficPolicy`.

With `externalTrafficPolicy: Local`, nodes without local Ready Pods **may intentionally be marked unhealthy**. Do not work around this by forcing traffic to all nodes without Pods; inspect Pod placement, replica counts, readiness, DaemonSets, service selectors, and locality policies.

## 14. Cloud Run Backends and Serverless NEGs: A Crucial Exception

When an external Application Load Balancer routes via a **serverless NEG** to Cloud Run, that backend **does not use a load balancer health-check resource like instance groups or zonal NEGs**. Do not hunt for firewall probe rules to Cloud Run to fix `unhealthy`.

When Cloud Run behind an LB returns 4xx/5xx:

- Verify the serverless NEG references the right service, region, and project.
- Verify the Cloud Run revision is deployed/ready, along with ingress and authentication settings.
- Inspect Cloud Run request logs, instance startup, memory/CPU, concurrency, and max instances.
- Verify the container listens on `PORT`, binds `0.0.0.0`, and completes startup.
- Check service-to-service IAM and confirm the frontend can invoke the backend in the deployed config.
- Check URL map host/path rules, serverless NEG, and default backend.

Cloud Run provides platform-level startup/liveness probes and readiness signals. They **do not** correspond to a `gcloud compute health-checks` resource attached to a serverless NEG. Confusing the two wastes significant operational time.

## 15. URL Maps, Routing, and 404/502/503 Errors

If DNS resolves and TLS succeeds yet HTTP returns errors, inspect the routing path:

~~~bash
gcloud compute forwarding-rules describe FORWARDING_RULE --global
gcloud compute target-https-proxies describe PROXY_NAME --global
gcloud compute url-maps describe URL_MAP_NAME --global
gcloud compute backend-services describe BACKEND_SERVICE --global
~~~

Switch to regional scope for regional LBs. External passthrough Network LBs do not have URL maps like this example.

### 15.1. Host/Path Mismatch

Suppose a URL map defines:

- `api.example.com/v1/*` → `api-v1-backend`.
- `api.example.com/v2/*` → `api-v2-backend`.
- Default service → static frontend.

If a client requests `www.example.com/v2/orders`, the hostname fails to match the host rule and falls through to the default backend even though TLS succeeded. Always inspect the actual **Host header** and request path, not just the intended backend name.

### 15.2. 502 and 503 Do Not Share the Same Cause

- **502:** typically indicates the LB failed to obtain a valid response from the backend due to connection close, timeout, or protocol mismatch.
- **503:** may indicate no healthy backends were available, capacity/connection limits were hit, or the application itself returned 503.
- **404:** may come from an unmatched URL map rule or a missing route in the app.

Never guess root cause from HTTP status alone. In Cloud Load Balancing request logs, inspect `jsonPayload.statusDetails` (where present) to distinguish backend-originated errors from LB-handled errors, alongside `httpRequest.status`, latency, and backend/forwarding-rule context.

Example Logs Explorer query for a global external LB:

~~~text
resource.type="http_load_balancer"
httpRequest.status>=500
~~~

Monitored resource types for regional Application LBs can differ (e.g., regional external LB). Match the exact resource type in existing logs, and configure request logging/sampling to gather enough evidence within budget.

### 15.3. Backend Timeouts and Draining

For long-lived or streaming requests:

- Backend service timeout may be shorter than request processing time.
- Client timeout may be shorter than LB timeout, or vice versa.
- Keepalive timeouts between proxy and backend may mismatch.
- Connection draining or rolling deployments may close active connections.
- GKE rolling updates or MIG recreates may temporarily reduce healthy endpoints.

Tune timeouts using latency distributions, request semantics, and SLOs rather than raising all timeouts to infinity.

## 16. TLS Security During Troubleshooting

### 16.1. Avoid Risky "Quick Fixes"

- Never use `curl -k` to declare a connection secure.
- Never disable certificate validation in production Java HTTP clients.
- Never paste private keys into chat, tickets, or repositories.
- Never downgrade an SSL policy to TLS 1.0/1.1 just for an old client.
- Never open application firewall ports to `0.0.0.0/0` when only probe/proxy subnets need access.
- Never strip domain-protecting CAA or DNSSEC records without understanding the root cause.
- Never modify multiple DNS/proxy/certificate resources simultaneously during an incident.

### 16.2. Protecting mTLS and Identity

When frontends or backends enforce mutual TLS:

- Confirm the exact TLS termination point.
- Verify trust stores, client CAs, and workload identities.
- Separate user-to-LB certificates from LB-to-backend certificates.
- Preserve audit logs for changes to certificate maps, SSL policies, forwarding rules, and firewalls.

Certificate rotation should follow **issue → attach → verify from client → observe → detach old**, accounting for propagation delays. Never confuse "resource exists" with "actively served."

## 17. End-to-End Diagnostic Command Suite

This is a **read-only** checklist for a global external HTTPS Application LB with an instance group backend. Adjust placeholders and scope per LB type; not every command applies to every LB.

~~~bash
# 1) DNS and certificates from the client side.
dig api.example.com A +short
dig api.example.com AAAA +short
dig api.example.com CAA
curl -vI https://api.example.com/
echo | openssl s_client -connect LB_IP:443 -servername api.example.com

# 2) Frontend, TLS proxy, and URL map.
gcloud compute forwarding-rules list --global
gcloud compute target-https-proxies describe PROXY_NAME --global
gcloud compute url-maps describe URL_MAP_NAME --global

# 3) Certificate resources (choose the applicable one or both).
gcloud compute ssl-certificates describe CERT_NAME --global
gcloud certificate-manager certificates describe CERT_NAME --location=global
gcloud certificate-manager maps entries list --map=MAP_NAME

# 4) Backends and health checks.
gcloud compute backend-services describe BACKEND_SERVICE --global
gcloud compute backend-services get-health BACKEND_SERVICE --global
gcloud compute health-checks describe HEALTH_CHECK --global

# 5) Compare with a direct-IP test preserving Host/SNI.
curl -v --resolve api.example.com:443:LB_IP https://api.example.com/
~~~

Archive results in the incident ticket with UTC timestamps and proper access controls. Never copy commands verbatim and run them against an unintended default project: pass `--project` explicitly and verify scope.

## 18. Runbook: HTTPS Domain Goes Down After DNS/Certificate Changes

**Scenario:** `api.example.com` uses a global external Application LB, a Certificate Manager Google-managed certificate, and GKE NEGs. During a DNS provider migration, some users see the old certificate while others hit DNS errors.

### Step 1: Confirm Impact

- Record affected client networks/locations, error frequency, SLO burn, and start time.
- Separate `NXDOMAIN`, TLS errors, and HTTP 5xx.
- Test the user-facing endpoint over both IPv4 and IPv6.

### Step 2: DNS

- Inspect NS at the registrar and run `dig +trace`.
- Compare authoritative A/AAAA records with the forwarding rule VIP.
- Check DS/DNSKEY if DNSSEC is enabled.
- Check TTLs, negative caching, and zone update timestamps.
- If using GeoDNS/CDNs, verify all public responses permit certificate authorization.

### Step 3: Certificate

- Open Certificate Manager and inspect `managed.state` and authorization attempts.
- Verify CNAME DNS authorization and CAA records if used.
- Check the certificate map entry for the exact hostname and target proxy.
- Run `openssl -servername` against old and new VIPs to check leaf cert, SANs, and expiration.
- Never delete the old cert until the new cert is proven live.

### Step 4: Backend

- If TLS succeeds yet the API returns 503, inspect URL map/backend service, `get-health`, and GKE Pods/NEGs.
- Separate firewall-blocked health probes from application readiness failures.
- Monitor Cloud Load Balancing and GKE request logs after changes.

### Step 5: Mitigation

- If only DNS is wrong and the old VIP still serves safely, evaluate rolling back delegation/records per runbook and known TTLs.
- If the new cert is not yet `ACTIVE`, keep the valid old frontend/cert in service while permitted.
- If backends are unhealthy after a rollout, roll back the revision/Deployment once evidence and data-safety conditions allow.
- Never roll DNS back to a decommissioned system or one holding unsynchronized stale data.

### Step 6: Verify Completion

1. Authoritative and public resolvers return the expected IP for both A and AAAA.
2. TLS verification passes with valid SANs, chain, and expiry without `-k`.
3. URL map routes to the intended backend.
4. Backend health meets thresholds; 502/503 spikes stop.
5. p95/p99 latency, error budget, and business KPIs return to acceptable ranges.
6. Observe through a soak period, and document propagation time and follow-up actions.

## 19. Java/Spring Boot Practice: Meaningful Health Endpoints

### 19.1. Actuator Configuration

With Spring Boot Actuator enabled:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
~~~

Example checks from an authorized environment:

~~~bash
curl -is http://127.0.0.1:8080/actuator/health/readiness
curl -is http://127.0.0.1:8080/actuator/health/liveness
~~~

If using Spring Security, configure request matchers and access rules compatible with health checkers without exposing all Actuator endpoints to the Internet. On Cloud Run, distinguish Cloud Run's startup/liveness probes from Application LB health checks on serverless NEGs (which do not exist).

### 19.2. Dependency Health: When Should It Report DOWN?

A readiness group may verify database connectivity if nearly all requests require the database. However:

- During a regional Cloud SQL outage, marking every instance `Unhealthy` does not make the database available again.
- If read-only/cached features remain usable, returning degraded behavior can be preferable to draining all backends.
- Liveness should not depend on external databases, avoiding restart storms.
- Never return 200 unconditionally once the application is no longer accepting traffic.

Strike this balance according to your readiness contract, SLOs, circuit breakers, and failover policies.

### 19.3. Post-Rollout Failure Example

A new Spring Boot build moves the readiness route from `/health` to `/actuator/health/readiness`. The GKE backend service still probes `/health`, turning all new Pods Unhealthy. Proper remediation:

1. Inspect the active LB health-check configuration.
2. Verify `/health` returns 404 and the new path returns 200 on the Pod IP.
3. Either update `BackendConfig`/health check or retain an alias path under change control.
4. Roll out progressively, waiting for Healthy status before scaling down old replicas.
5. Monitor LB logs, p99 latency, and error budget.

Never restart the entire cluster when only a health-check route changed.

## 20. Cloud Monitoring, Logging, and Alerting

### 20.1. Essential Signals

| Target | Metric/Observation | Meaning |
|---|---|---|
| Public endpoint | DNS resolution success, TLS expiry, HTTP success | End-to-end client/synthetic view |
| Load balancer | Request rate, 4xx/5xx, backend latency | Frontend symptoms |
| Backend service | Healthy/unhealthy backend count, utilization | Effective serving capacity |
| Health check | Probe successes/failures, state transitions | Firewall, path, port, or app faults |
| Certificate | Expiration, managed status, authorization failures | Rotation/renewal outage risk |
| GKE/MIG | Pod/instance readiness, CPU, OOM/restarts | Application health |
| Cloud Run | Request errors, instance count, startup failures | Serverless backend health |
| DNS | DNS error rate, authoritative/recursive probes | NXDOMAIN/SERVFAIL, broken delegation |

Not every metric exists with the same name or scope across every LB/backend. Build dashboards after verifying the exact monitored resource and metric in **Metrics Explorer**—never write an alert on a metric that your LB type does not emit.

### 20.2. Logs Explorer

Example filter for 5xx requests on a global external Application LB:

~~~text
resource.type="http_load_balancer"
httpRequest.status>=500
~~~

Inspect `jsonPayload.statusDetails`, backend name, latency, and request ID. For GKE/GCE/Cloud Run, check corresponding workload logs to verify whether requests reached the backend. In many setups, LB logging/sampling must be explicitly enabled first; missing logs do not mean zero requests.

### 20.3. Synthetic Probes and SLOs

Run external probes outside the LB infrastructure to verify:

- DNS resolution (A/AAAA, and DNSSEC where applicable).
- TLS certificate SAN/chain/expiry against the real hostname.
- GET on a stable HTTP 200 endpoint.
- Minimal synthetic business transactions if required.

Run synthetic probes from multiple locations/networks when global availability is required. Never rely solely on internal health checks, since they do not test DNS or frontend certificates.

### 20.4. Alert Noise

Page on-call for real user impact or loss of healthy capacity; send tickets/notifications for approaching certificate expiry, renewal errors, and DNS drift. Include domain, LB type, project, frontend VIP, backend service, region, runbook URL, and owner in every alert.

## 21. Diagnostic Scenarios and Exercises

### Scenario A: Certificate Stuck in `PROVISIONING`

A domain recently migrated from an old registrar to Cloud DNS, and the Certificate Manager cert remains `PROVISIONING`. Outline:

1. Checking NS/DS/SOA, authoritative DNS, and public resolvers.
2. Checking the exact DNS authorization CNAME from `dnsResourceRecord`.
3. Checking CAA records and failure reasons; for per-project auth, the allowed CA is `pki.goog`.
4. Checking `managed.state`, authorization attempts, and old certificate expiry.
5. Planning attach new / verify / detach old without deleting the currently active cert.

### Scenario B: IPv4 DNS Works Yet IPv6 Fails Certificate Validation

`curl -4` succeeds while `curl -6` returns a different certificate. Use `dig AAAA`, IPv6 forwarding-rule inventory, and `openssl -servername` against each VIP, and compare cert map attachments. Propose a fix for the AAAA record or IPv6 frontend along with TTL and rollback plans.

### Scenario C: GKE Rollout Leaves 0/X Backends Healthy

The app changed its Spring Actuator path while Ingress/`BackendConfig` still probes the old path. Identify:

- Commands to inspect backend health and health-check configuration.
- How to prove new Pods return 200 on the new path.
- How to roll out while preserving availability.
- Why changing `readinessProbe` does not automatically update the LB health check.

### Scenario D: LB Healthy Yet Users Receive 503

A regional external Application LB uses VM backends. Health checks from Google ranges pass, yet firewalls block traffic from the proxy-only subnet. Analyze both paths separately (probes vs. live traffic), firewall policies, and `statusDetails` without opening firewalls to the whole Internet.

### Scenario E: Cloud Run Behind a Serverless NEG

The backend has no health-check resource yet the API returns 503 under load. Inspect Cloud Run revisions, startup, max instances, concurrency, database pools, ingress/auth, and logs; explain why you do not create `gcloud compute health-checks` for a serverless NEG.

## 22. Production Checklist Before DNS/Certificate/LB Changes

### Pre-Change

- [ ] Identified LB type, scope (global/regional), and backend type.
- [ ] Recorded forwarding rule IP, target proxy, certificate/map, URL map, and backend service.
- [ ] Inventoried hostnames/SANs, A/AAAA/CNAME/CAA records, and authoritative NS.
- [ ] Checked DNSSEC/delegation; lowered TTLs ahead of cutover if needed.
- [ ] New certificate is ACTIVE and properly attached, while old cert remains ready for rollback.
- [ ] Health check matches app: port/path/Host/HTTP status/thresholds.
- [ ] Firewalls/NetworkPolicies allow exact probe CIDRs and proxy-only subnets where applicable.
- [ ] Tested frontend TLS, DNS, backend health, and synthetic requests.
- [ ] Confirmed change owner, window, rollback, incident contacts, and SLO guardrails.

### During Change

- [ ] Logged timestamps and config diffs.
- [ ] Applied one configuration group at a time and observed propagation.
- [ ] Verified `curl --resolve` with exact SNI and TLS validation without `-k`.
- [ ] Verified DNS resolvers/IPv6, URL map, and backend `get-health`.
- [ ] Monitored LB error rates, health-check logs, and backend logs.
- [ ] Did not ignore system errors just because health checks showed Healthy.
- [ ] Did not unconditionally open firewalls or weaken TLS security.

### Post-Change

- [ ] Domain resolves to the expected IP from authoritative and multiple recursive resolvers.
- [ ] TLS chain, issuer, SANs, expiry, and SNI are valid.
- [ ] Application meets HTTP success and business SLOs.
- [ ] Backends retain sufficient healthy capacity across rollouts and failover.
- [ ] Zero certificate renewal or DNS authorization errors remain.
- [ ] Alerts active for certificate expiry, DNS drift, unavailable backends, and 5xx spikes.
- [ ] Updated runbooks, asset inventory, and postmortem/action items.
- [ ] Cleaned up old certificates/forwarding rules **after** confirming zero remaining references.

## 23. Official References

- [Cloud Load Balancing overview](https://cloud.google.com/load-balancing/docs/load-balancing-overview)
- [Health checks overview and probe source ranges](https://cloud.google.com/load-balancing/docs/health-check-concepts)
- [Create and use health checks](https://cloud.google.com/load-balancing/docs/health-checks)
- [Troubleshooting Application Load Balancers](https://cloud.google.com/load-balancing/docs/https/troubleshooting)
- [Load balancing logging and statusDetails](https://cloud.google.com/load-balancing/docs/https/https-logging-monitoring)
- [Google-managed Compute Engine SSL certificates](https://cloud.google.com/load-balancing/docs/ssl-certificates/google-managed-certs)
- [Troubleshoot SSL certificates](https://cloud.google.com/load-balancing/docs/ssl-certificates/troubleshooting)
- [Certificate Manager troubleshooting](https://cloud.google.com/certificate-manager/docs/troubleshooting)
- [Certificate Manager global DNS authorization](https://cloud.google.com/certificate-manager/docs/deploy-google-managed-dns-auth)
- [Certificate Manager regional managed certificates](https://cloud.google.com/certificate-manager/docs/deploy-google-managed-regional)
- [Manage Certificate Manager certificate maps](https://cloud.google.com/certificate-manager/docs/map-entries)
- [Cloud DNS troubleshooting](https://cloud.google.com/dns/docs/troubleshooting)
- [Cloud DNS DNSSEC overview](https://cloud.google.com/dns/docs/dnssec)
- [GKE Ingress health checks](https://cloud.google.com/kubernetes-engine/docs/troubleshooting/ingress-health-checks)
- [GKE Service type LoadBalancer](https://cloud.google.com/kubernetes-engine/docs/concepts/service-load-balancer)
- [GKE BackendConfig CRD](https://cloud.google.com/kubernetes-engine/docs/how-to/ingress-configuration)
- [Cloud Run with external Application Load Balancer](https://cloud.google.com/load-balancing/docs/https/setting-up-https-serverless)
- [Cloud Monitoring documentation](https://cloud.google.com/monitoring/docs)
- [Cloud Logging documentation](https://cloud.google.com/logging/docs)
- [Spring Boot Actuator health endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)

## 24. Summary

To troubleshoot certificate, DNS, and load balancer health check errors on GCP, **work from the outside in**: verify DNS and the frontend IP; inspect TLS/SNI/certificate resources and attachments; confirm URL map and backend service routing; inspect health-check configuration and backend health; and finally check ports, firewalls, Pods/instances, and application behavior. At the same time, understand key differences across global/regional Application LBs, proxy/passthrough Network LBs, GKE Ingress, and Cloud Run serverless NEGs.

The right fix modifies **only the layer with verified failure evidence**, without weakening security or availability, and re-verifies from the client's perspective using DNS, TLS, and synthetic HTTP checks. Combining rollback-ready runbooks, Cloud Logging/Monitoring, safe certificate rotation, and rollout testing cuts both time-to-detect and the risk of repeat outages.
