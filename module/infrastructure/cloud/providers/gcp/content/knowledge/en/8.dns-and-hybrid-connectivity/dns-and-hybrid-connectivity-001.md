# Cloud DNS Public Zones and Record Management

A team is deploying an API on Google Cloud and wants customers to access it via the name `api.example.com` instead of an IP address. At the same time, the team needs to configure email, verify domain ownership, switch endpoints between releases without downtime, and restrict who is allowed to modify DNS. **Cloud DNS public managed zones** help manage authoritative DNS records for public domain names on the Internet.

This lesson belongs to the **DNS and Hybrid Connectivity** chapter of the **CLOUD_PROVIDERS_GCP** module. DNS connects knowledge of project organization, IAM, and VPC with deployment services such as Compute Engine, GKE, Cloud Run, Cloud Storage, and databases. Mastering public DNS helps you choose the right public endpoints, perform controlled releases, monitor reliability, and manage costs.

After this lesson, you will be able to:

- Explain authoritative name servers, registrars, delegation, public zones, recursive resolvers, and caching.
- Create a public managed zone and distinguish between a zone name and a DNS suffix.
- Manage A, AAAA, CNAME, MX, TXT, CAA, and NS RRsets according to their constraints.
- Use the Google Cloud Console, `gcloud`, and Terraform to add, modify, and inspect records.
- Plan TTL, DNS cutovers, DNSSEC, IAM permissions, and rollbacks.
- Analyze cases involving incorrect DNS records, missing delegation, or unexpired cache.

> **Example conventions:** `example.com` and its subdomains are documentation domains only; `203.0.113.0/24`, `198.51.100.0/24`, and `2001:db8::/32` are documentation IP ranges. Do not use them verbatim as real endpoints. To operate on the Internet, you need a domain name under your control and valid application addresses.

## 1. How Does Public DNS Work?

**DNS (Domain Name System)** uses a hierarchical mechanism to look up data associated with a domain name. For example, when an application needs the IP of `api.example.com.`, it usually queries a **recursive resolver**. The resolver returns a cached result if it is still valid; otherwise, it queries the root, TLD, and authoritative name servers to find the corresponding RRset.

~~~mermaid
flowchart LR
  A["Browser or application"] --> B["Recursive resolver"]
  B --> C["Root DNS"]
  C --> D["TLD .com"]
  D --> E["Authoritative NS of example.com"]
  E --> F["A / AAAA / CNAME record ..."]
  F --> B
  B --> A
~~~

The diagram shows the query chain when there is no cache. In practice, the resolver does not need to query every tier if it already has the name server name or RRset in its cache.

| Component | Role | Key Distinction |
|---|---|---|
| **Registrar** | Manages domain registration and provides the interface to update nameservers | Cloud DNS is not a domain registrar |
| **Parent DNS zone** | Contains NS records to delegate child domains | For `example.com`, the parent tier is in the `.com` DNS system |
| **Cloud DNS public zone** | Manages and serves authoritative records | A zone can exist even if the registrar does not yet point to Cloud DNS |
| **Authoritative name server** | Answers RRsets for the zone | Name servers assigned by Cloud DNS for the public zone |
| **Recursive resolver** | Resolves on behalf of clients and caches according to TTL | May still return old results after you update an RRset |
| **Application endpoint** | Receives connections once the client has the IP | Load balancer, website, or API; DNS does not serve HTTP itself |

**Key takeaway:** Creating a public managed zone in Google Cloud **does not automatically switch DNS for the domain**. You must update the NS delegation at the registrar or parent zone so that the Internet uses the authoritative NS assigned by Cloud DNS.

## 2. How Does a Public Zone Differ from a Private Zone?

Cloud DNS supports multiple resolution models. This lesson focuses on **public managed zones**.

| Criterion | Public Managed Zone | Private Managed Zone |
|---|---|---|
| Who can query it? | Resolvers on the Internet when a valid delegation path exists | Authorized VPCs according to configuration |
| Used for | Websites, APIs, mail, and public records | Internal services, private IPs, workloads inside a VPC |
| Resolution mechanism | Public authoritative DNS system | Internal Google Cloud resolution |
| Needs registrar update? | Yes, if the domain belongs to the public DNS system and needs delegation | No, does not follow the public registrar/parent model |
| Role of VPC | Does not govern who can read public records | Governs which networks can use the private zone |

A public managed zone is a resource belonging to a **Google Cloud project** for IAM and billing governance, but it is not tied to a single region like a VM or a Cloud Run service. A public record can syntactically contain a private IP, but that **does not make the private IP reachable over the Internet**.

For hybrid connectivity, public DNS only resolves public domain names; resolving internal hostnames between on-premises and GCP requires appropriate mechanisms such as private zones, DNS forwarding, peering, VPN, or Interconnect.

## 3. Zone Name, DNS Suffix, and Resource Record Set

### Two Very Different Names

- **Managed zone name** is the identifier used in the Google Cloud API/CLI, for example `corp-public`.
- **DNS suffix** is the domain name that the zone manages, for example `example.com.`. The trailing dot denotes a fully qualified domain name (*FQDN*).
- **Record name** is the name of an RRset in the zone, for example `api.example.com.`, which must fall under the DNS suffix.
- **Zone apex** is the root of the zone, for example `example.com.`.

When creating a public zone, Cloud DNS automatically creates **SOA** and **NS** records at the zone apex. Retrieve the actual authoritative NS set from Cloud DNS; do not manually overwrite the apex NS list assigned by the service.

### RRset Is the Unit of Operation

A **Resource Record Set (RRset)** combines a DNS name, record type, TTL, and one or more `RDATA` values. Example describing the data shape:

~~~yaml
name: api.example.com.
type: A
ttl: 300
rrdatas:
  - 203.0.113.10
  - 203.0.113.11
~~~

Both IPs with the same name and type belong to **a single A RRset**. To change the address list, you must update the existing value set properly. Adding a TXT record for the same name is separate from modifying the A RRset.

**CNAME constraint:** A CNAME cannot coexist with an RRset of any other type at the same name. Because the zone apex already has NS/SOA records, you cannot place a standard CNAME directly at the apex.

## 4. Common Record Types

| Type | Example RDATA | Purpose | Things to Remember |
|---|---|---|---|
| `A` | `203.0.113.10` | Name → IPv4 | Use an external static IP when pointing to a load balancer that needs stability |
| `AAAA` | `2001:db8::10` | Name → IPv6 | Only use when the endpoint actually serves IPv6 |
| `CNAME` | `example.com.` | Alias name → target name | Cannot share the same name with other record types |
| `MX` | `10 mail.example.net.` | Mail exchanger | Lower numbers usually have higher priority; the mail target must be configured |
| `TXT` | `"google-site-verification=DEMO"` | Domain verification, SPF/DKIM/DMARC | String content and quoting rules must be exact |
| `CAA` | `0 issue "letsencrypt.org"` | Specifies CAs allowed to issue certificates | Can affect TLS certificate issuance or renewal |
| `NS` | Authoritative name server names | Domain/subdomain delegation | Apex NS records are managed by Cloud DNS |
| `SOA` | Serial metadata, timers, and nameserver | Zone administrative information | Initialized by Cloud DNS at the apex |
| `SRV` | `10 20 443 service.example.com.` | Declares service, host, and port | Clients must support SRV |

Example of a website, API, and email system:

~~~text
example.com.           A        203.0.113.10
example.com.           AAAA     2001:db8::10
www.example.com.       CNAME    example.com.
api.example.com.       A        203.0.113.20
example.com.           MX       10 mail.example.net.
example.com.           TXT      "google-site-verification=DEMO"
_dmarc.example.com.    TXT      "v=DMARC1; p=none"
~~~

The table only illustrates record structure, not a production-ready mail configuration. SPF, DKIM, DMARC, and MX must follow your email provider's instructions. For example, DMARC `p=none` is primarily for monitoring; it does not actively reject spoofed emails.

**Apex and `www`:** Placing A/AAAA on `example.com.` and CNAME on `www.example.com.` is valid. Conversely, placing a CNAME directly on `example.com.` conflicts with NS/SOA at the apex. If you need to point the apex to an application, use a record mechanism supported by the endpoint, such as A/AAAA pointing to the frontend IP of an external load balancer.

## 5. Preparing and Creating a Public Managed Zone

Before creating a zone:

1. Select a Google Cloud project with billing enabled and clear ownership.
2. Enable the `dns.googleapis.com` API.
3. Ensure your identity is granted permission to create zones, such as `roles/dns.admin` at the required scope.
4. Identify domain management access at the registrar and who is authorized to update nameservers.
5. For an active domain, **inventory all existing records**: web, API, mail, verification, subdomains, DNSSEC, and TTLs.

### Creating via Console

In the Google Cloud Console, open **Network services → Cloud DNS → Create zone**, and select:

- **Zone type:** Public.
- **Zone name:** `corp-public` (administrative name).
- **DNS name:** `example.com.` (DNS suffix).
- **Description:** describe the purpose, owner, and environment.
- **DNSSEC:** choose according to requirements and the plan to update DS at the registrar.

After clicking Create, open the zone details to view the default NS and SOA records. This zone will not be used by the Internet for the domain until delegation is updated.

### Creating via gcloud

~~~bash
# Illustrative example only; replace with a project/domain under your control.
PROJECT_ID="my-dns-project"
ZONE="corp-public"
DOMAIN="example.com."

gcloud config set project "$PROJECT_ID"
gcloud services enable dns.googleapis.com

gcloud dns managed-zones create "$ZONE" \
  --dns-name="$DOMAIN" \
  --description="Public DNS for example.com" \
  --visibility=public \
  --labels="team=platform,environment=production"

gcloud dns managed-zones describe "$ZONE"
gcloud dns record-sets list --zone="$ZONE"
~~~

Do not run this verbatim against `example.com.`. Creating a public zone may incur **zone maintenance fees** even before the registrar is updated. The commands require appropriate permissions and API enablement.

## 6. Delegation: Helping the Internet Find the Right Authoritative NS

Once the public zone is created, Cloud DNS assigns a set of **authoritative name servers**. For public resolvers to use the new zone, the parent DNS must contain the appropriate **NS delegation**.

~~~text
Client queries api.example.com.
            ↓
Recursive DNS → root → .com
                       ↓
                NS of example.com.
                       ↓
            Cloud DNS authoritative NS
                       ↓
            A api.example.com. = endpoint IP
~~~

### Migrating an Active Domain

1. **Export the current zone** from the old provider; verify all RRsets, especially MX, TXT verification, DKIM, SPF, CAA, and subdomain NS records.
2. **Create a Cloud DNS public zone** with the same suffix and populate all data completely.
3. **Query the Cloud DNS NS directly** to confirm all critical records return the expected answers before cutover.
4. **Evaluate DNSSEC** if the old zone already has a DS record at the parent. Handle the chain of trust according to plan before switching nameservers.
5. **Update nameservers at the registrar** with the NS list provided by Cloud DNS. If migrating only a subdomain, add the NS delegation in the corresponding parent zone.
6. **Verify across multiple recursive resolvers** and monitor website/API/mail functionality; keep the old provider running long enough for old caches to expire.
7. **Decommission the old DNS infrastructure** once delegation, responses, and dependent systems are stable.

Cloud DNS does not automatically change NS records at the registrar. You may encounter a situation where `dig @<Cloud-DNS-NS>` returns the new answer while `dig` from the Internet still hits the old DNS: this usually means delegation has not been updated or caches have not yet expired their TTL.

### Delegating a Subdomain

For example, the platform team keeps `example.com.` and delegates `dev.example.com.` to the dev team:

~~~text
Parent zone: example.com.
  dev.example.com.      NS  (NS set of the child Cloud DNS zone)

Child zone: dev.example.com.
  app.dev.example.com.  A   203.0.113.30
~~~

Create the child zone first, obtain the exact NS list from Cloud DNS, and then create the NS RRset at `dev.example.com.` in the parent zone. Do not replace the child zone's apex NS/SOA with arbitrary names. When two zones are managed in different projects, coordinated ownership and approval processes are needed to avoid mismatched delegations.

## 7. TTL, Caching, and Change Propagation Delay

**TTL (Time To Live)** is the duration a resolver may cache an RRset. For example, a 300-second TTL allows caching for about 5 minutes; this **does not guarantee that every machine on the Internet sees the new record in exactly 5 minutes**, because multiple caching layers and delegation changes are involved.

Reasons updates appear slowly:

- Resolvers recently cached the old RRset with a large TTL before the update.
- Operating systems, browsers, or applications maintain their own caches.
- The parent zone and recursive resolvers cache old NS delegations.
- Previous queries returned `NXDOMAIN` or `NODATA`, causing **negative caching** based on the SOA record.
- Cloud DNS needs to process the change operation and synchronize authoritative servers; completing the operation still does not purge external caches.

| Scenario | Reference TTL | Explanation |
|---|---|---|
| Stable records | 1 hour or more | Reduces authoritative query frequency |
| Preparing endpoint cutover | A few minutes, after lowering TTL early enough | Enables faster cutover/recovery |
| MX, DNS verification | Per provider requirements | Do not change arbitrarily when systems depend on them |
| NS delegation | Per parent/registrar | Account for NS TTL outside the zone |

**Cutover planning:** If the old TTL is 3600 seconds, lower it to 300 **before** changing the IP and wait for the old TTL cache to expire. Lowering the TTL at the same time as changing the IP cannot force resolvers holding a 3600-second cached record to re-query immediately.

A low TTL is not completely free: it can increase query volume to authoritative servers and affect DNS costs. Do not use an excessively low TTL as a substitute for proper load balancing architecture or operational procedures.

## 8. Adding, Reading, and Modifying Records with gcloud

### Creating Basic Records

~~~bash
ZONE="corp-public"

gcloud dns record-sets create "example.com." \
  --zone="$ZONE" --type=A --ttl=300 \
  --rrdatas="203.0.113.10"

gcloud dns record-sets create "www.example.com." \
  --zone="$ZONE" --type=CNAME --ttl=300 \
  --rrdatas="example.com."

gcloud dns record-sets create "api.example.com." \
  --zone="$ZONE" --type=A --ttl=300 \
  --rrdatas="203.0.113.20"

gcloud dns record-sets list --zone="$ZONE"
~~~

These resource creation commands are for illustration only. If an RRset with the same name and type already exists, update the existing RRset; do not try to create an additional standalone `A` record with the same name. In the Console, **Add standard** creates a new RRset; edit the existing A RRset when you need to add a second IP to the same dataset.

### Replacing an IP Using a Transaction

Cloud DNS supports transactions consisting of multiple **remove** and **add** operations to apply a logically atomic change. Suppose `api.example.com.` currently has an A RRset containing a single IP `203.0.113.20` and TTL 300:

~~~bash
ZONE="corp-public"
RECORD="api.example.com."

# Read back before replacing: parameters must match the existing RRset exactly.
gcloud dns record-sets list --zone="$ZONE" \
  --filter="name=$RECORD"

gcloud dns record-sets transaction start --zone="$ZONE"

gcloud dns record-sets transaction remove "203.0.113.20" \
  --zone="$ZONE" --name="$RECORD" --type=A --ttl=300

gcloud dns record-sets transaction add "198.51.100.20" \
  --zone="$ZONE" --name="$RECORD" --type=A --ttl=300

gcloud dns record-sets transaction execute --zone="$ZONE"
gcloud dns record-sets list --zone="$ZONE"
~~~

**Note:** Before removing, retrieve the **exact TTL and complete RDATA** of the old RRset; if it has two IPs, you must handle the entire set rather than guessing one value. Transactions should not be created concurrently by multiple users in the same directory sharing the default `transaction.yaml` file; in pipelines, use a job-specific transaction file or deploy via API/IaC with concurrency control.

Check the change operation and re-read the zone before retrying if an error occurs. Do not create a new record with the wrong name or switch Project IDs to work around an error message.

### Managing TXT, MX, and CAA

- Multiple TXT values on the same name belong to a single TXT RRset; when adding a new verification token, do not delete tokens used by other services.
- MX contains a **priority** and mail server hostname; modifying MX requires coordination with the email provider and monitoring deliverability.
- SPF, DKIM, and DMARC all involve TXT records; only use values confirmed by the mail team.
- CAA can affect CA issuance of TLS certificates: modifying CAA must account for renewals.
- A CNAME record cannot share the same name as other TXT/A/MX records and cannot be placed at the zone apex.

## 9. Managing DNS with Terraform and the Review Process

Organizations typically use Infrastructure as Code to store DNS configuration in Git and grant write permissions only to a dedicated pipeline:

~~~hcl
resource "google_dns_managed_zone" "public" {
  name        = "corp-public"
  dns_name    = "example.com."
  description = "Public DNS managed by platform"
  visibility  = "public"

  labels = {
    team        = "platform"
    environment = "production"
  }
}

resource "google_dns_record_set" "root_a" {
  managed_zone = google_dns_managed_zone.public.name
  name         = google_dns_managed_zone.public.dns_name
  type         = "A"
  ttl          = 300
  rrdatas      = ["203.0.113.10"]
}

resource "google_dns_record_set" "www_cname" {
  managed_zone = google_dns_managed_zone.public.name
  name         = "www.example.com."
  type         = "CNAME"
  ttl          = 300
  rrdatas      = ["example.com."]
}

resource "google_dns_record_set" "api_a" {
  managed_zone = google_dns_managed_zone.public.name
  name         = "api.example.com."
  type         = "A"
  ttl          = 300
  rrdatas      = ["203.0.113.20"]
}
~~~

This example omits provider/state backend, TLS, DNSSEC, email, and quotas; it is meant to show how zones and RRsets are declared. If a zone already exists, you must **import** it and reconcile state with the running resource rather than creating a duplicate zone with the same suffix and ending up with unwanted new NS records.

Recommended change workflow:

1. A developer opens a pull request containing the record name, type, RRdata, TTL, reason, and target endpoint.
2. CI checks syntax, CNAME conflicts, domain ownership, and `terraform plan`.
3. Platform DNS and application owners review; changes to MX/NS/CAA/DNSSEC require additional stakeholders.
4. The pipeline uses a service account with restricted IAM permissions to run `terraform apply`, logging who approved and when the change was made.
5. Verify against authoritative NS and recursive resolvers; monitor the application and confirm.

Do not manage the same RRset simultaneously via Terraform and manual tools without a synchronization process; drift can cause the next apply to overwrite manual changes. Inspect `plan` very carefully if there is any replace or delete action on a **managed zone**, because recreating it can result in a different NS set.

## 10. IAM and Change Control for Public DNS

Anyone with DNS write permissions can redirect website traffic, disrupt email, or manipulate domain verification records. Therefore, production DNS permissions must be strictly governed.

| Group | Required Permissions | How to Assign Permissions |
|---|---|---|
| Platform DNS administrator | Create zones, configure DNSSEC, modify critical RRsets | Appropriate Cloud DNS admin permissions, e.g., `roles/dns.admin` in a controlled project |
| Developer | View and propose changes | Read permissions or PR workflow |
| DNS deployment pipeline | Apply approved RRsets | Dedicated service account with least privilege |
| Security/Audit | View IAM and change history | Corresponding read and audit permissions |
| Registrar administrator | Modify NS/DS at the registrar | Registrar account, independent of Google Cloud IAM |

IAM has **inheritance** from Organization/Folder/Project. If `dns.admin` is granted at a Folder level, removing local permissions at the project level may **not** revoke effective access. You must review principals, group memberships, Allow/Deny/PAB policies where applicable, and permissions required to access the DNS API.

To reduce risk, place public DNS in a dedicated governance project, manage IAM via groups, separate application deployment identities from DNS modification identities, and enforce peer review and audit logging for production. Do not grant DNS edit permissions just because a developer already has permission to deploy Cloud Run.

## 11. DNSSEC: Protecting Response Authenticity

**DNSSEC** signs zone data so supporting resolvers can verify the authenticity and integrity of responses. DNSSEC helps protect against spoofing/cache poisoning, but **does not encrypt DNS query contents** and does not replace HTTPS/TLS.

For DNSSEC to work with a complete chain of trust:

1. Enable DNSSEC for the public zone in Cloud DNS.
2. Retrieve the **DS record** associated with the zone's DNSKEY.
3. Publish the DS record at the **registrar/parent zone** as instructed.
4. Verify on a resolver with DNSSEC validation; monitor for any `SERVFAIL` issues.

Example of viewing the DS record:

~~~bash
gcloud dns dns-keys list \
  --zone="corp-public" \
  --filter="type=keySigning" \
  --format="value(ds_record())"
~~~

If DNSSEC is enabled on the zone without publishing a valid DS record, the chain of trust is incomplete. If the DS at the parent **does not match** the keys used after changing NS or rotating keys, validating resolvers may return `SERVFAIL`, making the domain unresolvable.

**Disabling DNSSEC must be done in the right order:** remove the DS record at the registrar/parent, wait for resolvers to pick up the change according to TTL, verify, and only then disable DNSSEC on the public zone. Never turn off zone signing while an old DS record is still active. Switching DNS providers on a domain with DNSSEC enabled requires a dedicated DS coordination plan.

## 12. Routing Policies Are Not HTTP Load Balancing

Beyond standard records, Cloud DNS supports routing policies such as **weighted round robin (WRR)**, **geolocation**, and **failover** with supported endpoint types and configurations.

| Policy | Intended Use | Limitations |
|---|---|---|
| WRR | Select responses based on weights | Resolver caching can cause actual traffic ratios to differ from weights |
| Geolocation | Return records based on where the DNS query originates | Query origin may be the resolver or EDNS Client Subnet, not necessarily the end user |
| Failover | Select a backup endpoint when configuration supports health checks | Health checks, endpoint types, and firewalls must be compatible |

DNS answers names per query, not per individual HTTP request. Resolvers can cache and share answers across many users, so DNS cannot guarantee an exact 10% canary split of application traffic. When you need TLS, host/path-based routing, HTTP health checks, or DDoS/WAF protection, consider an External Application Load Balancer and point `A/AAAA` to the load balancer's stable frontend IP.

## 13. Verifying Resolution and Changes with dig

After modifying an RRset, always check both the **authoritative NS** and **recursive resolvers**.

~~~bash
# Inspect managed configuration and change history in Cloud DNS.
ZONE="corp-public"
gcloud dns managed-zones describe "$ZONE"
gcloud dns record-sets list --zone="$ZONE"
gcloud dns record-sets changes list --zone="$ZONE"

# Replace CLOUD_DNS_ASSIGNED_NS with the actual authoritative NS returned by describe.
dig @CLOUD_DNS_ASSIGNED_NS A api.example.com. +noall +answer

# Check delegation and recursive resolvers.
dig NS example.com. +noall +answer
dig +trace api.example.com.
dig @8.8.8.8 A api.example.com. +noall +answer
dig @1.1.1.1 A api.example.com. +noall +answer
dig @8.8.8.8 MX example.com. +noall +answer
~~~

**Interpreting results:** If the authoritative NS is correct but public resolvers return old data, check caching and delegation. If the new authoritative NS itself is wrong, check the RRset and change operation. If `dig +trace` still directs to the old provider's NS, the registrar/parent has not been updated or resolvers are still holding the old delegation.

### Logging and Monitoring

Cloud DNS allows enabling query logging at the **public managed zone** level:

~~~bash
gcloud dns managed-zones update "corp-public" --log-dns-queries
~~~

Queries that **actually reach the authoritative name servers** can be written to Cloud Logging; responses served from cache by external resolvers do not traverse the name servers and will not generate new query logs. You can create **log-based metrics** for response codes, query name/type, or query volume and build dashboards/alerts in Cloud Monitoring. DNS query data can contain sensitive metadata; control viewing permissions, retention periods, and Cloud Logging costs.

Watch for signals such as unusual spikes in `NXDOMAIN`, `SERVFAIL` when DNSSEC is enabled, sudden surges in query volume, 5xx/timeout errors at the load balancer after a cutover, or out-of-band record set changes.

### Costs

Cloud DNS has a **managed zone fee based on how long the zone exists** and a **per-query fee**, which may have a different unit price for queries using routing policies. Zone fees may still apply even when there are no queries or before delegation. There is no universal Cloud DNS free tier. Logging and Monitoring incur separate usage-based charges. Use labels for cost allocation, inspect Cloud Billing, and set budget alerts; budget alerts **do not automatically block queries or delete zones**.

## 14. Common Troubleshooting

| Symptom | Possible Cause | How to Check |
|---|---|---|
| RRset exists in Cloud DNS, but Internet doesn't see it | Delegation does not point to Cloud DNS NS | `dig NS`, `dig +trace` |
| Authoritative returns new, external resolvers return old | Cache TTL / negative caching | Query NS directly and check remaining TTL |
| Cannot add CNAME | Same name already has A/TXT/MX or is the apex | List all RRsets with the same name |
| Cannot create zone | API not enabled, missing IAM, invalid name | Check Cloud DNS API and CLI error details |
| A record is correct, but HTTPS fails | Endpoint, certificate, or host mapping misconfigured | Check load balancer/Cloud Run and TLS |
| Email breaks after cutover | Missing MX, SPF/DKIM/DMARC, or old NS still cached | Compare records against mail configuration |
| `SERVFAIL` after enabling DNSSEC | DS/DNSKEY mismatch | Verify DS at registrar/parent and keys in the zone |
| Cannot delete zone | User records or dependencies still exist | Inventory, export data, and safely remove delegation |
| Costs rise even after application is shut down | Zone still exists or still receiving queries/logging | Billing breakdown by zone, queries, and Logging |

### Production API Cutover Example

The API is currently using `203.0.113.20` and needs to switch to `198.51.100.20`:

1. Deploy the new endpoint and verify HTTPS, certificates, health checks, and application behavior before touching DNS.
2. Lower the TTL early enough and wait for caches with the old TTL to expire.
3. Export a snapshot of the old RRset; confirm the cutover window, owner, and rollback plan.
4. Update the A record via a transaction or reviewed Terraform change.
5. Query authoritative NS and recursive resolvers; monitor application errors and latency.
6. If issues occur, revert to the old RRset while **keeping both endpoints alive** during the period when resolvers hold different cached results.
7. Once stable, raise the TTL back to the normal value and clean up the old endpoint as planned.

**DNS rollback is not instantaneous.** Data in external caches can persist for a while, so cutover reliability depends far more on parallel-run planning and endpoint verification than on a single DNS update command.

## 15. Scenario: Website, API, and Mail on Google Cloud

An e-commerce company operates a website, a Java API, and a mail system:

~~~text
Cloud DNS public zone: example.com.
  example.com.       A       203.0.113.10       → External LB website
  www.example.com.   CNAME   example.com.       → Website
  api.example.com.   A       203.0.113.20       → External LB API
  example.com.       MX      10 mail.example.net. → Mail provider
  example.com.       TXT     verification...     → Domain verification
~~~

The platform team owns the DNS project and manages delegation and DNSSEC. Application teams deploy Compute Engine/GKE/Cloud Run behind load balancers in dev/staging/prod projects. Production DNS changes go through pull requests and a dedicated pipeline with restricted IAM. The mail team confirms MX/TXT before switching NS; SRE monitors HTTP error rates, latency, and query logs after changes.

When an application needs a private database inside a VPC or an on-premises server, a public zone neither establishes network connectivity nor resolves private names automatically. In that case, you need to design private DNS, inbound/outbound forwarding, and hybrid network connectivity as required.

## 16. Checklist and Practice Exercises

- [ ] Identified the registrar, parent zone, owner, and current NS.
- [ ] Cloud DNS project has clear billing, IAM, and ownership.
- [ ] Zone name is distinct from the DNS suffix, and Cloud DNS-initialized NS/SOA records are preserved.
- [ ] A/AAAA/CNAME/MX/TXT/CAA records and child delegations are inventoried.
- [ ] No CNAME shares a name with another RRset or sits at the apex.
- [ ] Endpoints and TLS are independently verified before cutover.
- [ ] Snapshot, planned TTL, cutover schedule, and rollback plan are in place.
- [ ] DNSSEC and DS at the registrar/parent are consistent if used.
- [ ] Verified authoritative NS, `dig +trace`, and multiple recursive resolvers.
- [ ] Review workflow for production DNS and dedicated CI/CD permissions are established.
- [ ] Query logging, monitoring, zone/query costs, and logging costs are accounted for.
- [ ] Before decommissioning a zone, delegation is migrated and dependent services are verified.

**Practice exercise:** An enterprise manages the domain `company.example.`, needs `www` pointing to an external load balancer for its website, `api` pointing to an external load balancer for a Java service, email via an external provider, and the dev team managing `dev.company.example.` through a child public zone. Do the following:

1. Draw the delegation tree across the registrar, parent zone, and child zone, indicating which NS records are automatically created by Cloud DNS.
2. Design the RRsets and TTLs for the website, API, MX, TXT, and the child zone's NS.
3. Write `gcloud` commands to create the public zone, A/CNAME records, read the zone, and inspect change operations.
4. Describe how to migrate the API to a new IP with a TTL-lowering window, testing, and rollback.
5. Explain why DNS does not immediately work publicly just by creating a zone in the Console.
6. Propose IAM roles for platform, developers, and pipelines so that not everyone has `roles/dns.admin`.
7. Explain the impact if the registrar holds an old DS record that does not match the DNSKEY of the new zone.

## Official References

- [Cloud DNS overview](https://cloud.google.com/dns/docs/overview) — service capabilities and public/private zones.
- [Create, modify and delete zones](https://cloud.google.com/dns/docs/zones) — creating zones and default NS/SOA.
- [Add, update, and delete records](https://cloud.google.com/dns/docs/records) — RRsets, transactions, CNAME.
- [Set up DNS records for a domain](https://cloud.google.com/dns/docs/set-up-dns-records-domain-name) — configuration and delegation.
- [DNSSEC configuration](https://cloud.google.com/dns/docs/dnssec-config) — enabling and disabling DNSSEC.
- [Activate DNSSEC at registrar](https://cloud.google.com/dns/docs/registrars) — DS and chain of trust.
- [DNS routing policies and health checks](https://cloud.google.com/dns/docs/routing-policies-overview) — WRR, geolocation, and failover.
- [Cloud DNS logging and monitoring](https://cloud.google.com/dns/docs/monitoring) — query logging and monitoring changes.
- [Cloud DNS pricing](https://cloud.google.com/dns/pricing) — zone and query costs.
- [gcloud dns reference](https://cloud.google.com/sdk/gcloud/reference/dns) — CLI syntax.
