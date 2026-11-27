# Static Website Project with Cloud Storage, HTTPS, and CDN

A product landing page, documentation site, event page, or frontend built into HTML, CSS, and JavaScript typically does not need a continuously running Java server to serve those files to browsers. Google Cloud lets you store static files in **Cloud Storage**, use an **Application Load Balancer** to serve a custom domain over **HTTPS**, and enable **Cloud CDN** to distribute content from edge caches near users.

This project guides you through building a small static website, deploying it into a dedicated Cloud Storage bucket, connecting it to a global external Application Load Balancer, configuring a Google-managed TLS certificate, pointing DNS, and testing caching, security, cost, and update workflows. Next, we add a Cloud Build pipeline so releases no longer depend on manual uploads.

This lesson belongs to the **GCP Hands-On Projects** chapter of the **CLOUD_PROVIDERS_GCP** module. The module helps learners explore Google Cloud from projects, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage, and databases; through deployment scenarios, learners practice selecting services, securing resources, automating releases, and monitoring reliability and cost. In this project, concepts across IAM, DNS, TLS, caching, CI/CD, and FinOps are connected into a system that can be tested from a browser.

> **Cost and Safety Note:** The commands below are instructions for you to run in your own lab project; this lesson does not automatically create Google Cloud resources. Load balancers, public IPs, CDN, storage, and network traffic can incur charges even with very low traffic. Only run after selecting the right project, enabling Billing, and setting a budget alert. Do not store credentials, internal data, or secret source code in a public bucket.

## Objectives

After completing this project, you will be able to:

- Describe the request path from a visitor to DNS, the HTTPS load balancer, Cloud CDN, and Cloud Storage.
- Create a static HTML/CSS/JavaScript website with a home page, subpage, and error page.
- Create a bucket, upload files, set content types, configure index/error pages, and set appropriate access permissions.
- Create a backend bucket, enable Cloud CDN, configure a URL map, external IP, and HTTPS frontend.
- Provision a Google-managed TLS certificate and point DNS for a domain.
- Test HTTPS, cache headers, status codes, releases, and rollbacks.
- Design `Cache-Control` policies to balance load speed with updatability.
- Automate uploads using Cloud Build with least-privilege permissions.
- Monitor costs, logs/metrics, and safely clean up lab resources.

## 1. Product Scope and Acceptance Criteria

Suppose the team needs a service landing website named **GCP Demo Site** with the illustrative domain **www.example.com**. This domain is only an example; you must own or manage a real domain to complete the DNS and HTTPS certificate steps.

**Minimum functionality:**

1. Home page with a title, description, and link to the about page.
2. About page accessible via a specific static path.
3. Responsive CSS and small interactive JavaScript.
4. Custom error page for non-existent paths.
5. Content served only over the chosen domain with valid HTTPS.
6. Cloud CDN enabled on the backend bucket.
7. A way to release a new version, verify caching, and restore a previous version.

**Technical criteria:**

| Item | Acceptance Condition |
|---|---|
| Storage | Files exist in the lab bucket in the right project |
| Routing | Root URL returns the home page; static files load properly |
| HTTPS | Certificate is ACTIVE/valid, hostname matches |
| CDN | Backend bucket has Cloud CDN enabled; cache policy is explicit |
| Security | Contains public data only; deploy permissions separated from read access |
| Error handling | Non-existent paths return the proper error response |
| Release | Content updates reach users according to the cache policy |
| Operations | Tests, metrics, budget, and cleanup procedures are in place |

### Scope Boundaries

Cloud Storage **does not execute Java/Spring Boot code, PHP, or server-side dynamic request processing**. A static website can run JavaScript in the browser and call dynamic APIs hosted separately on Cloud Run/GKE/Compute Engine. If an application requires authentication, sessions, or private user data, design a separate backend and authorization layer instead of placing that data in static files.

## 2. Target Architecture

~~~mermaid
flowchart LR
    U["Browser"] --> DNS["DNS: www.example.com"]
    DNS --> IP["Global external IP"]
    IP --> LB["External Application Load Balancer<br/>HTTPS + Google-managed certificate"]
    LB --> MAP["URL map"]
    MAP --> CDN["Backend bucket<br/>Cloud CDN enabled"]
    CDN --> GCS["Cloud Storage<br/>index.html, CSS, JS, images"]
    CI["Cloud Build<br/>deploy identity"] --> GCS
    MON["Cloud Monitoring / Billing"] -.-> LB
    MON -.-> CDN
~~~

**Layer-by-layer breakdown:**

| Component | Responsibility | What needs to be managed? |
|---|---|---|
| DNS | Maps hostname to load balancer IP | Appropriate A/AAAA/CNAME records, TTL, and zone admin permissions |
| Global external IP | Static address for the frontend | Reserve/release, billing |
| Application Load Balancer | Receives HTTPS requests and routes them | Frontend, forwarding rule, TLS proxy, URL map |
| Google-managed TLS certificate | Serves valid certificates for the domain | Domain validation, provisioning, renewal, and status |
| Backend bucket | Connects the URL map to Cloud Storage | Backend bucket name and policy |
| Cloud CDN | Caches content at the edge per HTTP semantics | Cache mode, TTL, invalidation, and metrics |
| Cloud Storage | Origin storing HTML/CSS/JS/assets | Objects, IAM, metadata, storage location |
| Cloud Build | Uploads verified artifacts to the bucket | Trigger, build service account, approval |

Cloud Storage has an object caching mechanism, but enabling Cloud CDN on a backend bucket gives you additional cache policies and invalidation capabilities. The CDN does not modify origin content; it retains copies according to caching rules.

### Why Does HTTPS Require a Load Balancer?

Cloud Storage can serve content via Google Storage endpoints, but a **website using a custom domain with HTTPS** requires an appropriate frontend solution. In this lesson, the Application Load Balancer terminates TLS for your domain, then fetches files from the backend bucket. The certificate is attached to the HTTPS frontend, **not installed on Cloud Storage objects**.

### Load Balancer Version

This lab uses a **global external Application Load Balancer** with the **EXTERNAL_MANAGED** load balancing scheme. Google Cloud also supports classic Application Load Balancers and some regional models with backend buckets, but commands and flags differ across types. When practicing, pick **one type** and use all corresponding resources consistently; do not mix classic EXTERNAL commands with an EXTERNAL_MANAGED forwarding rule.

## 3. Prerequisites

You need:

- A Google Cloud project for the lab, linked to Billing.
- A domain or subdomain where you have permission to edit DNS records.
- Google Cloud CLI installed, authenticated, and set to the project.
- Permissions to create Cloud Storage buckets/objects and configure load balancing/certificates as appropriate.
- Permission to modify DNS at your domain registrar or DNS provider.
- A machine with a browser, `curl`, and a shell environment supporting the illustrative commands.

### IAM Considerations

| Activity | Reference Role/Permission | Desired Scope |
|---|---|---|
| Create bucket and website config | Appropriate Cloud Storage admin permissions | Lab project only |
| Upload artifacts | `roles/storage.objectAdmin` or equivalent least-privilege permission | Website bucket only |
| Read public files | `allUsers` with object read access in the public origin option | Approved public bucket only |
| Create IP/LB/URL map/certificate | Compute Network Admin and related Compute permissions | Lab project only |
| View Monitoring/Billing | Appropriate Viewer roles for observability/cost systems | Relevant resources only |

Specific roles depend on your organization and existing permissions. Do not grant Owner/Editor to a build service account just to run an upload step. The person creating the load balancer may need different permissions from the person authoring content.

### Enable APIs

Using a confirmed lab project:

~~~bash
export PROJECT_ID="your-lab-project-id"
export REGION="asia-southeast1"
export DOMAIN="www.your-owned-domain.example"

gcloud config set project "$PROJECT_ID"
gcloud services enable \
  compute.googleapis.com \
  storage.googleapis.com \
  cloudbuild.googleapis.com \
  --project="$PROJECT_ID"
~~~

`DOMAIN` is where you supply a real hostname you control DNS for; do not use the literal `*.example` string to attempt certificate issuance. Choose the bucket location based on user geography, residency, and cost; an HTTPS backend on a global load balancer does not require the bucket to be in the same region as every visitor.

### Set Cost Limits

Before creating billable resources:

1. Create a budget for the lab project and configure alerts at approved thresholds.
2. Record the list of IPs, forwarding rules, backend buckets, and buckets to be created.
3. Define a lab expiration date and the person responsible for cleanup.
4. Limit the number of invalidations and uploaded file sizes.
5. Do not run large-scale automated load tests against a public site without setting limits first.

Budget alerts **do not automatically stop costs from accruing**. For a lab, both cost monitoring and proactive cleanup are required.

## 4. Preparing the Static Website Source

A simple structure:

~~~text
static-site/
├── site/
│   ├── index.html
│   ├── about/
│   │   └── index.html
│   ├── 404.html
│   ├── assets/
│   │   ├── style.css
│   │   └── app.js
│   └── images/
│       └── logo.svg
└── cloudbuild.yaml        # Added in the CI/CD section
~~~

The example uses plain static HTML to focus on GCP. If you use React/Vue/Angular, build the production output into a `dist/` folder before uploading; avoid uploading `node_modules`, sensitive source maps, `.env` files containing secrets, or unnecessary source files.

### site/index.html

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Static website on Google Cloud">
  <title>GCP Demo Site</title>
  <link rel="stylesheet" href="/assets/style.css">
</head>
<body>
  <header class="container">
    <nav aria-label="Main navigation">
      <a href="/">Home</a>
      <a href="/about/">About</a>
    </nav>
  </header>
  <main class="container">
    <h1>Hello from Google Cloud</h1>
    <p>Static website stored in Cloud Storage and distributed via HTTPS + CDN.</p>
    <button type="button" id="hello-button">Test JavaScript</button>
    <p id="message" role="status"></p>
  </main>
  <footer class="container">GCP Demo Site — demo version</footer>
  <script src="/assets/app.js" defer></script>
</body>
</html>
~~~

### site/assets/style.css

~~~css
:root {
  color-scheme: light;
  font-family: system-ui, sans-serif;
  background: #f7f9fc;
  color: #18324a;
}
body {
  margin: 0;
  line-height: 1.6;
}
.container {
  width: min(92%, 960px);
  margin: 0 auto;
  padding: 1.5rem 0;
}
nav {
  display: flex;
  gap: 1rem;
}
a {
  color: #1557b0;
}
button {
  padding: .65rem 1rem;
  border: 1px solid #1557b0;
  border-radius: .4rem;
  background: #fff;
  cursor: pointer;
}
~~~

### site/assets/app.js

~~~javascript
const button = document.querySelector("#hello-button");
const message = document.querySelector("#message");

if (button && message) {
  button.addEventListener("click", () => {
    message.textContent = "JavaScript loaded successfully on the static website.";
  });
}
~~~

### site/about/index.html

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>About — GCP Demo Site</title>
  <link rel="stylesheet" href="/assets/style.css">
</head>
<body>
  <main class="container">
    <nav><a href="/">Back to home</a></nav>
    <h1>About</h1>
    <p>This project uses Cloud Storage, HTTPS, and Cloud CDN.</p>
  </main>
</body>
</html>
~~~

### site/404.html

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Page Not Found</title>
</head>
<body>
  <h1>404 — Page Not Found</h1>
  <p><a href="/">Return to home page</a></p>
</body>
</html>
~~~

When running locally, use a simple HTTP server to check paths and CSS/JS. For example, if Python is available on your development machine, you can run `http.server` to serve the `site` folder; however, that is optional for local testing and not required for setting up Cloud Storage hosting.

For SPAs using history routing, deep links such as `/orders/123` may not exist as objects. Configure URL rewrite/error fallback or use a hosting layer that supports SPAs; avoid turning all 404 errors into 200 responses that mask genuinely missing resources. This lesson uses **multipage static HTML** so 404 works with proper semantics.

## 5. Creating the Cloud Storage Bucket and Website Configuration

Cloud Storage bucket names must be globally unique across all of Google Cloud. Choose a name that contains no sensitive data and is used only for the test website. In the commands below, replace the placeholder string with an available name.

### 5.1 Choosing Configuration Variables

~~~bash
export PROJECT_ID="your-lab-project-id"
export REGION="asia-southeast1"
export SITE_BUCKET="your-unique-static-site-bucket"

gcloud config set project "$PROJECT_ID"
echo "Project: $PROJECT_ID"
echo "Bucket:  $SITE_BUCKET"
~~~

Do not proceed if the project is unexpectedly a production project. A bucket with "lab" in its name can still reside in a production project; verify the project via `gcloud` and the Console.

### 5.2 Creating the Bucket

~~~bash
gcloud storage buckets create "gs://$SITE_BUCKET" \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --default-storage-class=STANDARD \
  --uniform-bucket-level-access
~~~

**Uniform bucket-level access (UBLA)** lets you manage object permissions via bucket-level IAM instead of combining multiple object ACLs. This is the easier-to-manage option for the lab. If the bucket already exists, do not re-run the create command; check the bucket name, location, IAM, and owner before proceeding.

### 5.3 Uploading Content

From the `static-site` directory containing `site/`:

~~~bash
gcloud storage rsync --recursive ./site "gs://$SITE_BUCKET"

gcloud storage ls "gs://$SITE_BUCKET"
gcloud storage ls "gs://$SITE_BUCKET/assets/"
~~~

`rsync` updates objects from local to the bucket. **Do not add destination-deletion flags** without carefully reviewing the exact file list; other releases or resources may already exist in the bucket.

Cloud Storage stores files under their corresponding keys:

~~~text
gs://BUCKET/index.html
gs://BUCKET/404.html
gs://BUCKET/about/index.html
gs://BUCKET/assets/style.css
gs://BUCKET/assets/app.js
~~~

### 5.4 Checking MIME Types

Correct `Content-Type` helps browsers interpret data accurately:

| Extension | Common Content-Type |
|---|---|
| .html | text/html; charset=utf-8 |
| .css | text/css |
| .js | text/javascript |
| .svg | image/svg+xml |
| .png | image/png |
| .webp | image/webp |

The CLI can auto-detect file types during upload, but you should verify object metadata:

~~~bash
gcloud storage objects describe "gs://$SITE_BUCKET/index.html"
gcloud storage objects describe "gs://$SITE_BUCKET/assets/style.css"
gcloud storage objects describe "gs://$SITE_BUCKET/assets/app.js"
~~~

If metadata is wrong, update the corresponding object:

~~~bash
gcloud storage objects update \
  "gs://$SITE_BUCKET/index.html" \
  --content-type="text/html; charset=utf-8"

gcloud storage objects update \
  "gs://$SITE_BUCKET/assets/style.css" \
  --content-type="text/css"
~~~

Do not blindly set every object to `text/html`. When CSS/JS is returned with the wrong `Content-Type` and browsers enforce MIME sniffing protection, the UI may fail to load properly.

### 5.5 Configuring Main and Error Pages

~~~bash
gcloud storage buckets update "gs://$SITE_BUCKET" \
  --web-main-page-suffix=index.html \
  --web-error-page=404.html

gcloud storage buckets describe "gs://$SITE_BUCKET"
~~~

For static websites, `MainPageSuffix` resolves directory paths such as `/about/` to `about/index.html` when handled by a website-serving endpoint. `NotFoundPage` displays `404.html` when an object does not exist. Always test live through the HTTPS load balancer rather than relying solely on metadata.

**Do not confuse endpoint types:** `gs://` paths are for object management; website endpoints and HTTPS load balancers handle HTTP requests according to their respective configurations. A direct Cloud Storage API URL does not necessarily exhibit the same redirect/index/error behavior as the website hostname.

## 6. Choosing a Content Read Model: Public Bucket vs. Private Bucket

The website in this lesson is public content, so one simple approach is allowing reads on objects in a **bucket containing only public assets**. Google Cloud also supports **private bucket access through Cloud Load Balancing and Cloud CDN** with dedicated configuration, suitable when an organization wants to prevent users from accessing the origin directly.

### Option A — Public Bucket for Public Content

To allow browsers and edge caches to read public content with simple instructions, grant:

~~~bash
gcloud storage buckets add-iam-policy-binding \
  "gs://$SITE_BUCKET" \
  --member=allUsers \
  --role=roles/storage.objectViewer
~~~

**Security warning:** `roles/storage.objectViewer` at the bucket level for `allUsers` allows reading objects and can also allow listing object metadata/names. This is only appropriate for a **bucket dedicated exclusively to fully public files**. Never place `.env`, tokens, backups, private source code, source maps containing sensitive data, or customer data in this bucket.

If public access prevention (PAP) is enforced on the bucket or via Organization Policy, adding `allUsers` may be rejected. **Do not disable organization-level policies to bypass lab errors**; request an appropriately scoped exception from an administrator if approved, or switch to the private bucket access model.

### Option B — Private Origin via Load Balancer/CDN

Private bucket access is an advanced architecture with dedicated permissions for the frontend and backend bucket. It allows serving public content through the load balancer/CDN while blocking origin access via ordinary `allUsers` permissions. This model must be configured according to the specific guide for the Application Load Balancer and Cloud CDN setup in use.

In this option:

- Do not grant `allUsers` directly on the bucket.
- Configure private bucket access per official documentation.
- Verify the HTTPS frontend can still read objects while direct access to the origin is denied.
- Review signed URLs or signed cookies if non-public content control is required; do not treat Cloud CDN caching as application authentication.

To stay focused on learning DNS, TLS, and caching, the commands that follow assume **Option A is approved**. If your project belongs to an organization with strict PAP enforcement, choose Option B instead of trying to reuse the `allUsers` command verbatim.

## 7. Creating the Global External IP and Backend Bucket

At this point, Cloud Storage is only the origin. We need an HTTPS frontend and URL map so the website appears on the chosen hostname.

### 7.1 Naming the Resources

~~~bash
export IP_NAME="site-global-ip"
export BACKEND_BUCKET="site-backend"
export URL_MAP="site-url-map"
export TLS_CERT="site-managed-cert"
export HTTPS_PROXY="site-https-proxy"
export HTTPS_RULE="site-https-forwarding"

export DOMAIN="www.your-owned-domain.example"
~~~

Choose different names if the lab project already has resources with those names. Record the chosen names in your report so you only clean up what the lab created and avoid deleting someone else's resources.

### 7.2 Reserving a Global Static IP

~~~bash
gcloud compute addresses create "$IP_NAME" \
  --network-tier=PREMIUM \
  --ip-version=IPV4 \
  --global \
  --project="$PROJECT_ID"

gcloud compute addresses describe "$IP_NAME" \
  --global \
  --project="$PROJECT_ID" \
  --format="get(address)"
~~~

Save the IP result in your lab notes. When pointing DNS, use this IP; do not set an `A` record to a random address or to a Cloud Storage API IP address.

### 7.3 Creating the Backend Bucket and Enabling Cloud CDN

~~~bash
gcloud compute backend-buckets create "$BACKEND_BUCKET" \
  --gcs-bucket-name="$SITE_BUCKET" \
  --enable-cdn \
  --project="$PROJECT_ID"

gcloud compute backend-buckets describe "$BACKEND_BUCKET" \
  --project="$PROJECT_ID"
~~~

A backend bucket is a Cloud Load Balancing resource pointing to a Cloud Storage bucket; it is **not** a second Cloud Storage bucket. With CDN enabled, eligible responses are cached at the edge per the cache policy. Confirm that the backend bucket shows CDN enabled.

### 7.4 Creating the URL Map

~~~bash
gcloud compute url-maps create "$URL_MAP" \
  --default-backend-bucket="$BACKEND_BUCKET" \
  --project="$PROJECT_ID"
~~~

The URL map selects a backend based on hostname and path. For a single website, a default backend bucket is sufficient. When you later need to add a dynamic API running on Cloud Run, you can add a backend service/serverless NEG and matching host/path rules; this lesson does not need that configuration yet.

## 8. HTTPS Frontend and TLS Certificate

### 8.1 Provisioning a Google-Managed Certificate

~~~bash
gcloud compute ssl-certificates create "$TLS_CERT" \
  --domains="$DOMAIN" \
  --global \
  --project="$PROJECT_ID"
~~~

The example command uses a **global Compute Engine Google-managed SSL certificate**. Certificate Manager also supports Google-managed certificates and has its own domain authorization methods. The two certificate management options have different workflows for attaching to an HTTPS proxy; do not create a Certificate Manager certificate and try to attach it using flags meant only for Compute SSL certificates.

Creating the certificate does not mean it is ready yet. Google must validate the domain, and provisioning can take time after DNS is pointed properly to the frontend. Do not launch to production while the certificate status is not yet valid.

### 8.2 Creating the Target HTTPS Proxy

~~~bash
gcloud compute target-https-proxies create "$HTTPS_PROXY" \
  --url-map="$URL_MAP" \
  --ssl-certificates="$TLS_CERT" \
  --project="$PROJECT_ID"
~~~

The HTTPS proxy binds the URL map to the TLS certificate. The certificate must match the hostname clients use; if the website serves both `example.com` and `www.example.com`, you need a certificate covering those names and matching DNS/frontend configuration.

### 8.3 Creating the Global Forwarding Rule for Port 443

~~~bash
gcloud compute forwarding-rules create "$HTTPS_RULE" \
  --load-balancing-scheme=EXTERNAL_MANAGED \
  --network-tier=PREMIUM \
  --address="$IP_NAME" \
  --global \
  --target-https-proxy="$HTTPS_PROXY" \
  --ports=443 \
  --project="$PROJECT_ID"
~~~

Current request path:

~~~text
https://www.your-owned-domain.example
    → global static IP : 443
    → target HTTPS proxy + managed TLS certificate
    → URL map
    → Cloud CDN-enabled backend bucket
    → Cloud Storage origin
~~~

This lesson only configures a port 443 frontend. If you want users typing `http://` to be automatically redirected to `https://`, configure an additional HTTP port 80 frontend **with a URL redirect to HTTPS**, rather than creating an HTTP frontend that directly serves unencrypted content. This can be done via the Console or a separate redirect URL map per Application Load Balancer documentation.

## 9. Pointing DNS and Verifying the Certificate

After reserving the IP and creating the HTTPS frontend, update DNS for the hostname you own:

| DNS Field | Illustrative Value |
|---|---|
| Type | A |
| Name | www |
| Value | Newly reserved global external IPv4 |
| TTL | Per DNS policy, e.g., 300 seconds during cutover |

If using a root/apex domain, create an `A` record for that exact hostname at your DNS provider. `CNAME` points to a **hostname**, not directly to an IP address. If you want IPv6 support, add the appropriate IPv6 address/forwarding rule and corresponding `AAAA` record; never create an `AAAA` record pointing to an IPv4 address.

### Checking DNS

~~~bash
nslookup "$DOMAIN"
~~~

The result should resolve to the reserved IP. DNS changes can take time due to TTL and resolver caches; do not rely on a single machine's DNS cache to conclude propagation is complete everywhere.

### Checking Certificate Status

~~~bash
gcloud compute ssl-certificates describe "$TLS_CERT" \
  --global \
  --project="$PROJECT_ID" \
  --format="yaml(name,managed.status,managed.domainStatus,managed.domains)"
~~~

Wait for the certificate to reach provisioned/ACTIVE status for the actual domain before confirming HTTPS is ready. If provisioning stalls, check that DNS points to the right IP, the hostname is covered by the certificate, the frontend is healthy, and the domain can be validated.

### Checking HTTPS and Static Files

~~~bash
curl -I "https://$DOMAIN/"
curl -I "https://$DOMAIN/index.html"
curl -I "https://$DOMAIN/about/"
curl -I "https://$DOMAIN/assets/style.css"
curl -I "https://$DOMAIN/not-found-test"
~~~

Expect root/index/about/CSS to return appropriate success responses and missing resource requests to return 404. With a properly configured frontend, browsers should report a valid certificate for the hostname and zero mixed-content warnings.

**Note:** HTTP status codes and custom 404 pages through Cloud Storage/backend buckets can depend on the endpoint and actual URL routing. If you encounter `403` for a missing object path, inspect permissions and website/not-found response behavior before blaming the CDN. Test both `/about/` and `/about/index.html` to verify index suffix behavior.

### Testing Before Global DNS Propagation Completes

With the IP reserved and the certificate ACTIVE, you can use `curl --resolve` to direct an HTTPS request to a specific IP while preserving the hostname for TLS:

~~~bash
export FRONTEND_IP="REPLACE_WITH_RESERVED_IPV4"
curl --resolve "$DOMAIN:443:$FRONTEND_IP" \
  -I "https://$DOMAIN/"
~~~

Replace `FRONTEND_IP` with the actual assigned IP. This method **does not bypass TLS validation** and does not make an unprovisioned certificate valid; it only lets you test the path to the target frontend.

## 10. Designing a Cache Policy for Cloud CDN

Cloud CDN can reduce load times and origin reads when content is cached. However, for frequently updated websites, poorly configured caching can cause users to see stale versions even after new objects have uploaded successfully.

### Cache-Control: Understand Before Setting TTL

| Directive | Practical Meaning | Use Case |
|---|---|---|
| `public` | Allows shared caches to store eligible responses | Public static files |
| `max-age=N` | Allows keeping the response fresh for N seconds | CSS, JS, images, or HTML as needed |
| `no-cache` | Cache may store the response but must revalidate before reuse | HTML that needs to pick up new releases |
| `no-store` | Do not store the response in directive-compliant caches | Sensitive or non-storable content |
| `immutable` | Hints that the resource will not change during the URL's lifetime | Content-hashed asset filenames |
| `s-maxage=N` | TTL for shared caches such as CDNs | When edge TTL should differ from browser TTL |

If `Cache-Control` metadata is omitted, Cloud Storage may supply a default response such as `public,max-age=3600` for public objects; therefore **do not leave TTL to defaults**. Cloud CDN determines cacheability based on MIME type, status code, headers, and backend cache mode, not just `.js` or `.html` extensions.

### Recommended Policy for the Lab

| Object | Suggested Policy | Reason |
|---|---|---|
| `index.html` | `public, no-cache, max-age=0, must-revalidate` | Prioritize fast content updates |
| `404.html` | `public, no-cache, max-age=0` | Do not hold error pages for long |
| `about/index.html` | `public, no-cache, max-age=0` | HTML pages may change |
| Unhashed `assets/style.css` and `app.js` | `public, max-age=300` | Avoid staying stale too long when filenames do not change |
| Content-hashed `assets/app.a1b2c3.js` | `public, max-age=31536000, immutable` | New URL when content changes; safe to cache long-term |
| Fixed-name images | `public, max-age=3600` or as needed | Reduce origin reads; weigh update frequency |

These are starting values for learning operations, not a universal policy for every organization. With long-term hashed assets, the build workflow must generate new filenames whenever files change and update HTML to reference the new names.

### Updating Object Metadata

~~~bash
gcloud storage objects update \
  "gs://$SITE_BUCKET/index.html" \
  --cache-control="public,no-cache,max-age=0,must-revalidate"

gcloud storage objects update \
  "gs://$SITE_BUCKET/404.html" \
  --cache-control="public,no-cache,max-age=0,must-revalidate"

gcloud storage objects update \
  "gs://$SITE_BUCKET/about/index.html" \
  --cache-control="public,no-cache,max-age=0,must-revalidate"

gcloud storage objects update \
  "gs://$SITE_BUCKET/assets/style.css" \
  --cache-control="public,max-age=300"

gcloud storage objects update \
  "gs://$SITE_BUCKET/assets/app.js" \
  --cache-control="public,max-age=300"
~~~

Verify headers after updating:

~~~bash
curl -I "https://$DOMAIN/index.html"
curl -I "https://$DOMAIN/assets/app.js"
~~~

You should see the expected `Cache-Control`, accurate `Content-Type`, and appropriate response statuses. Under some policies, older cached responses may persist in browsers/edges until TTL expires or they are invalidated; updating metadata does not always flush existing caches immediately.

### Cache Mode and Public Content

Common cache modes include `USE_ORIGIN_HEADERS`, `CACHE_ALL_STATIC`, and `FORCE_CACHE_ALL`. For public websites, start with origin headers or an appropriate static caching policy. **`FORCE_CACHE_ALL`** can override origin anti-cache directives and is unsafe for personalized data; only use it when guaranteed that all backend content is safe for public caching.

In the **private bucket access** model, Cloud CDN documentation specifies particular cache mode requirements. When switching architectures, review the official docs rather than assuming public bucket policies transfer unchanged.

## 11. Verifying That Cloud CDN Caching Actually Works

Enabling CDN does not mean every request is guaranteed to be a cache hit. The first request usually fetches from the origin; subsequent requests can hit if the object is eligible, fresh, and not evicted.

### Command-Line Testing

~~~bash
curl -I "https://$DOMAIN/assets/style.css"
curl -I "https://$DOMAIN/assets/style.css"
curl -I "https://$DOMAIN/assets/style.css"
~~~

Inspect headers such as `Cache-Control`, `Age` if present, `Content-Type`, and status. The `Age` header can indicate a response came from cache, though **not every cached response includes `Age`, and a single header is not enough to measure hit ratio accurately**.

### Testing via Cloud Monitoring

In Cloud Monitoring and the Cloud CDN/Load Balancing pages:

1. Select the matching backend bucket and URL map.
2. View request volume and cache hit/miss ratios where metrics are available.
3. Observe bytes served from cache versus origin.
4. Compare repeated requests after the cache has been warmed.
5. Check latency and response codes; never optimize hit ratio while users are receiving error content.

If Cloud CDN logging is enabled, choose an appropriate log sampling rate for diagnostics. Do not turn on full logging for every request under high traffic without evaluating costs and potential sensitive data in URLs.

### Cache Misses Are Not Always Errors

Common causes include:

- First request at a given edge location.
- Object is uncacheable due to headers, MIME type, or status.
- TTL expired, entry was evicted, or content was invalidated.
- URL has differing query strings and cache key policy treats them as distinct objects.
- Cookies/Authorization or headers altering cacheability.
- Mismatch between CDN policy and origin metadata.

Do not chase maximum cache hit ratio at any cost. A well-cached stale HTML response linking to deleted assets causes real breakage for users.

## 12. Releasing a New Version and Invalidating Cache

Suppose the design team updates the home page headline:

~~~html
<h1>Hello from Google Cloud — updated release</h1>
~~~

A manual release cycle:

1. Review changes and run local tests.
2. Upload new assets to the bucket.
3. Upload HTML pages pointing to the required assets.
4. Re-apply `Cache-Control` metadata if the upload workflow alters metadata.
5. Test HTTPS URLs with `curl` and a browser.
6. If the cache policy does not update fast enough, invalidate **only the specific paths**.

### Targeted Cache Invalidation

Example invalidating two specific URLs (without purging the entire cache):

~~~bash
gcloud compute url-maps invalidate-cdn-cache "$URL_MAP" \
  --path="/index.html" \
  --host="$DOMAIN" \
  --global \
  --project="$PROJECT_ID"

gcloud compute url-maps invalidate-cdn-cache "$URL_MAP" \
  --path="/" \
  --host="$DOMAIN" \
  --global \
  --project="$PROJECT_ID"
~~~

The paths `/` and `/index.html` may be two separate cache keys. If the site serves both root and index files directly, review URL rewriting/cache key policies so user-facing paths are not missed.

**Do not default to invalidating `/*` on every commit.** Invalidation can have costs or usage quotas, and broad invalidations can trigger origin request spikes. For production sites, prefer content-hashed assets and short HTML TTLs over constant full purges.

### Versioned Assets and Rollback

When using a bundler (Vite/Webpack or similar tools), it can produce:

~~~text
assets/app.8f2c3d.js
assets/style.4e5a7b.css
~~~

A new release generates new hash names; new HTML points to the new files. Old assets should be retained long enough for users who still have tabs open with the previous HTML. Do not delete old assets immediately after publishing if they are still referenced from caches or loaded pages.

To roll back, restore a **verified artifact set** (HTML and matching assets) and confirm the CDN serves the expected version. Do not roll back `index.html` alone if some of its referenced assets were already deleted. You can store release artifacts in a CI/CD artifact store or a separate internal bucket with appropriate retention.

### Why Treat a Static Website as a Release Artifact?

Uploading individual objects to Cloud Storage is not an atomic directory-wide transaction. If HTML is uploaded before new assets are ready, users can hit temporary 404s. A solid release workflow should:

- Build an immutable artifact bundle.
- Validate links/references and file existence before releasing.
- Upload assets first, HTML entrypoints second.
- Switch metadata/cache or traffic only after smoke tests pass.
- Retain previous releases for rollback.

For the small lab site, `rsync` across the whole directory is sufficient to learn the flow. For production, a stricter ordered publish and rollback process is needed.

## 13. Automating with Cloud Build

Manual uploads are prone to targeting the wrong project or bucket, missing files, or omitting metadata. Cloud Build can run validation checks and upload artifacts whenever changes merge into an approved branch.

### CI/CD Design

~~~mermaid
flowchart LR
    A["Commit/merge"] --> B["Cloud Build trigger"]
    B --> C["Validate static files"]
    C --> D["Build frontend if needed"]
    D --> E["Upload assets → HTML"]
    E --> F["Check metadata/cache"]
    F --> G["Smoke test HTTPS"]
    G --> H["Release report"]
~~~

The build service account only needs upload/metadata permissions on the bucket and necessary log-writing permissions. **It does not need permissions to create DNS, TLS certificates, or load balancers** for each release; infrastructure resources should be managed through IaC or a separate platform workflow.

### Simple cloudbuild.yaml

The file below is for a repo whose `site/` directory already contains HTML/CSS/JS:

~~~yaml
substitutions:
  _SITE_BUCKET: your-unique-static-site-bucket

steps:
  - id: validate-site
    name: gcr.io/google.com/cloudsdktool/google-cloud-cli:stable
    entrypoint: bash
    args:
      - -ceu
      - |
        test -f site/index.html
        test -f site/404.html
        test -f site/assets/style.css
        test -f site/assets/app.js
        echo "Static site input checks passed"

  - id: publish-assets
    name: gcr.io/google.com/cloudsdktool/google-cloud-cli:stable
    entrypoint: bash
    args:
      - -ceu
      - |
        gcloud storage cp \
          site/assets/style.css \
          gs://$_SITE_BUCKET/assets/style.css
        gcloud storage cp \
          site/assets/app.js \
          gs://$_SITE_BUCKET/assets/app.js
        gcloud storage objects update \
          gs://$_SITE_BUCKET/assets/style.css \
          --cache-control="public,max-age=300"
        gcloud storage objects update \
          gs://$_SITE_BUCKET/assets/app.js \
          --cache-control="public,max-age=300"
    waitFor:
      - validate-site

  - id: publish-html
    name: gcr.io/google.com/cloudsdktool/google-cloud-cli:stable
    entrypoint: bash
    args:
      - -ceu
      - |
        gcloud storage cp \
          site/about/index.html \
          gs://$_SITE_BUCKET/about/index.html
        gcloud storage cp \
          site/404.html \
          gs://$_SITE_BUCKET/404.html
        gcloud storage cp \
          site/index.html \
          gs://$_SITE_BUCKET/index.html
        gcloud storage objects update \
          gs://$_SITE_BUCKET/index.html \
          gs://$_SITE_BUCKET/404.html \
          gs://$_SITE_BUCKET/about/index.html \
          --cache-control="public,no-cache,max-age=0,must-revalidate"
    waitFor:
      - publish-assets

options:
  logging: CLOUD_LOGGING_ONLY

timeout: 600s
~~~

The example uses explicit files to clearly show uploading assets before HTML. For larger sites, use a sync command with controlled deletion and metadata handling, or publish versioned releases. Do not auto-delete old files in a simple release.

In `cloudbuild.yaml`, `$_SITE_BUCKET` is a Cloud Build **custom substitution**. When passing an actual shell variable inside a bash command, you may need to escape dollars with `$$` per Cloud Build substitution rules. Never put passwords or tokens into substitutions.

### Configuring the Build Identity

The workflow typically involves:

1. Create a user-specified build service account.
2. Grant object write permissions on the **website bucket**, not project-wide if unnecessary.
3. Grant Cloud Logging write permissions when using `CLOUD_LOGGING_ONLY`.
4. Create a trigger that runs only from protected branches or release tags.
5. Restrict editing build configs and triggering production releases to approved people/automation.
6. Verify the build cannot modify other buckets or delete networking resources.

Example manual run in the lab project:

~~~bash
gcloud builds submit . \
  --project="$PROJECT_ID" \
  --config=cloudbuild.yaml \
  --region="$REGION" \
  --substitutions="_SITE_BUCKET=$SITE_BUCKET"
~~~

The CLI uses the build identity configured on the build/trigger; if your environment requires specifying a build service account, configure it per current documentation and ensure the principal has proper permissions. Builds will fail without upload permission; **do not** work around this by granting Editor/Owner.

### Automated Post-Release Smoke Testing

A pipeline can run smoke tests once the certificate and DNS are active:

~~~bash
curl --fail --silent --show-error \
  "https://$DOMAIN/index.html" > /dev/null

curl --fail --silent --show-error \
  "https://$DOMAIN/assets/style.css" > /dev/null
~~~

In practice, check content/version markers and report clearer diagnostics than a bare `curl` call. If the cache has not refreshed yet, tests should distinguish between "origin published incorrectly" and "CDN is serving the prior version within its valid TTL".

## 14. Static Website Security and Public Data Boundaries

Cloud Storage + CDN serves public content efficiently, but that does not eliminate application security responsibilities.

### 14.1 Controlling Bucket Content

Do not upload:

- API keys authorized for sensitive operations, database passwords, private keys, or service account JSON files.
- `.env` files, `.git`, internal source code, backups, logs, or dumps containing customer data.
- Source maps exposing unapproved internal source code or paths.
- User-uploaded files that have not passed security validation and sanitization.
- Spring Boot or Java backend configuration files containing credentials.

Every JS/HTML/JSON file on a public website can be downloaded and read by anyone. **Minification, obfuscation, or hard-to-guess filenames do not protect secrets.**

If the frontend must call a separate API on Cloud Run:

1. Host the API on a separate hostname like `api.example.com` or use intentional path routing.
2. Enforce authentication and authorization on the backend, not by hiding buttons in JavaScript.
3. Configure CORS when frontend and API have different origins; CORS does not replace authorization.
4. Never store backend credentials in static files.
5. Apply rate limits, quotas, and logging commensurate with risk.

### 14.2 Content Security Policy and HTTP Security Headers

The site can apply headers such as:

| Header | Role |
|---|---|
| `Content-Security-Policy` | Restricts allowed sources for scripts, styles, images, and other resources |
| `X-Content-Type-Options: nosniff` | Reduces risk of incorrect MIME type interpretation |
| `Referrer-Policy` | Controls referrer information shared across navigations |
| `Strict-Transport-Security` | Instructs browsers to keep using HTTPS once established |
| `Permissions-Policy` | Restricts certain browser capabilities |

These headers must be configured at an HTTP serving layer that supports them, such as a response header policy on the load balancer or an appropriate frontend service. Do not assume Cloud Storage can set arbitrary response headers solely via a single object metadata field.

Apply HSTS carefully once HTTPS is stable across all relevant hostnames. Do not enable `includeSubDomains` or `preload` if other subdomains are not ready to serve HTTPS.

### 14.3 Protecting Deployment Permissions

For a public-origin bucket, read and write are completely different privileges:

- `allUsers` should only have read access on an approved public bucket.
- The build identity has permission to upload and update metadata on that exact bucket.
- Infrastructure administrators manage the LB, certificates, and DNS.
- Log/metrics viewers do not inherently have permission to modify the website.

Separate staging and production environments with appropriate buckets or projects. Never let pull requests from untrusted branches run with a service account authorized to publish directly to the production website.

### 14.4 Limitations of Public Origin

If a bucket is made public via `allUsers`, users can access the Cloud Storage endpoint directly once they know the bucket/object name, bypassing your HTTPS load balancer. Therefore:

- CDN, TLS policies, or WAF on the load balancer are **not the sole access boundary** for a public origin.
- Do not use a public bucket to hold documents you intend to expose only through an authenticated frontend.
- When traffic must be forced through the load balancer/CDN, switch to private bucket access per Google Cloud documentation.

This is why choosing between public and private origin must be driven by your threat model, not just command simplicity.

## 15. Monitoring, Logging, and Version Tracking

Even a static website can fail: expired certificates, mispointed DNS, deleted objects, HTML referencing old assets, misconfigured CDN caching, or unexpected cost spikes.

### Minimum Dashboard

| Group | Signals to Watch | Purpose |
|---|---|---|
| Load balancer | Request count, 4xx/5xx, latency | Detect routing or origin failures |
| Cloud CDN | Cache hit/miss, cache egress/origin fetch | Evaluate cache effectiveness |
| Cloud Storage | Object count, bytes stored, operations | Detect storage growth or unusual reads |
| TLS/DNS | Certificate status, DNS resolution, HTTPS synthetic check | Detect domain unavailability |
| Cloud Build | Build status, release ID, and publisher | Correlate changes with incidents |
| Billing | Cost by project and service | Catch unplanned charges |

Not every metric is available immediately before logging is enabled or when traffic is very low. Choose metrics suited to the active resources and size logging/sampling appropriately.

### Synthetic Monitoring

An external check can issue GET requests to:

~~~text
https://www.your-owned-domain.example/
https://www.your-owned-domain.example/about/
https://www.your-owned-domain.example/assets/style.css
~~~

Check status, TLS validity, content markers, and timeout. Checking load balancer health alone without fetching actual pages will miss broken CSS/JS asset references.

### Release Metadata

Each release should record:

- Source commit SHA.
- Cloud Build ID.
- Artifact checksum or manifest.
- UTC release timestamp.
- Bucket and URL map.
- Person or trigger executing the release.
- Smoke test results.
- Reference to the previous release for rollback.

A version label displayed in the footer or an HTML comment can help identify which version a user is receiving. Never include sensitive internal details like private repository tokens or secret paths in public metadata.

## 16. Cost Estimation and Optimization

The benefit of static hosting is not having to run a VM or Java process 24/7. However, an HTTPS + load balancer + CDN architecture has multiple billable components.

~~~text
Monthly static website cost
  = Cloud Storage capacity and operations
  + Application Load Balancer and forwarding rules
  + Cloud CDN cache egress and cache fill (per applicable pricing model)
  + related network egress and transfer
  + Cloud DNS if using a paid managed zone
  + Cloud Logging / Monitoring based on usage
  + CI/CD and security services if applicable
~~~

Do not treat this formula as an exact invoice, since pricing depends on region, pricing tier, traffic volume, cache hit ratio, and current terms. Consult official pricing tables and use the Google Cloud Pricing Calculator before long-term deployment.

### Quantitative Questions for Estimation

1. How many GB of objects does the website have?
2. How many page views occur per day?
3. What is the average page load size across HTML/CSS/JS/images?
4. Which regions do users come from, and can the CDN cache those objects?
5. How many deploys or cache invalidations happen per month?
6. How long are logs and metrics retained?
7. Does the load balancer run continuously or only during the lab?

### Approximate Traffic Calculation Example

Suppose **each page load transfers an average of 1 MiB** and there are **100,000 page loads/month**:

~~~text
Data served to clients ≈ 100000 MiB
                       ≈ 97.7 GiB / month
~~~

This is only an estimate of bytes served to browsers, **not** origin egress volume or the exact CDN bill. Browser caching, edge caching, revalidation, asset reloads, and user geography all affect actual charges. If 70% of data is served from edge caches, origin bytes read may drop, though actual metrics are needed for accurate forecasting.

### Optimizing Without Breaking Correctness

- Optimize images to WebP/AVIF where browser support fits.
- Compress or minify CSS/JS and drop unused dependencies.
- Set long TTLs for immutable assets; keep HTML updatable.
- Avoid unnecessary broad invalidations.
- Use content-hashed assets and release manifests.
- Apply appropriate retention/lifecycle rules to old versions without deleting assets still referenced.
- Set a budget and review actual costs after a representative load cycle.

Do not set an ultra-long cache policy on `index.html` just to chase a high cache hit ratio if users need timely updates or critical fixes.

## 17. Common Troubleshooting

| Symptom | Possible Cause | How to Check |
|---|---|---|
| DNS does not resolve to LB IP | Wrong A record, TTL, or edited wrong DNS zone | `nslookup`/`dig` and authoritative zone name |
| Certificate not yet ACTIVE | Domain not pointing to frontend yet, validation/provisioning pending | Certificate `status`/`domainStatus` |
| HTTPS hostname mismatch error | Certificate does not cover hostname | SAN/domains and accessed URL |
| Home page returns 403 | Origin permission/PAP or wrong backend route | Bucket IAM, public/private access, and URL map |
| Home page returns 404 | Missing `index.html` at root or wrong website config | Object list, `MainPageSuffix`, request path |
| `/about/` fails while `/about/index.html` loads | Routing/index suffix mismatch | Website config and LB behavior |
| CSS/JS fails to load | Missing file, wrong path, wrong `Content-Type` | DevTools Network tab and object metadata |
| Site still shows old version | Browser cache, CDN TTL, or object not uploaded | `Cache-Control`, `Age`, release ID, and CDN metrics |
| Low cache hit rate | Short TTL, uncacheable file, varying URL/query | Cache mode, headers, and response type |
| CDN accidentally caches sensitive data | `FORCE_CACHE_ALL` or public response containing personal data | Halt release, inspect policy, fix origin, invalidate scoped paths |
| Cloud Build permission denied | Build SA lacks bucket or log permissions | IAM on bucket and actual service account |
| Broken after deploy despite upload success | HTML/assets out of sync or old files deleted | Build manifest, smoke test, artifact rollback |
| Bill rises despite low traffic | LB/IP still running, logging, or cache fills/egress | Billing breakdown and resource inventory |

### Investigation Sequence

1. Check DNS and certificate status.
2. Check forwarding rule → HTTPS proxy → URL map → backend bucket.
3. Verify objects exist with the right access permissions.
4. Inspect status codes and response headers on the exact hostname.
5. Compare origin objects, cache policy, and release version.
6. Check Cloud CDN metrics/logs if available.
7. If an issue appears right after a release, consider rolling back before changing project-wide permissions.

Avoid changing DNS, bucket IAM, and cache policy simultaneously before isolating the root cause; changing multiple variables at once destroys traceability.

## 18. Safely Cleaning Up Lab Resources

Once the learning project is done, clean up billable resources **only when certain they belong exclusively to this lab**. A common mistake is deleting a URL map or bucket shared with another website.

### Inventory Before Deleting

~~~bash
gcloud config get-value project

gcloud compute forwarding-rules describe "$HTTPS_RULE" \
  --global \
  --project="$PROJECT_ID"

gcloud compute backend-buckets describe "$BACKEND_BUCKET" \
  --project="$PROJECT_ID"

gcloud storage buckets describe "gs://$SITE_BUCKET"
~~~

Cross-check every name against the resource inventory recorded at the beginning. If resources are serving organizational traffic or do not belong to the lab, **do not delete them**.

### Dependency Order

Once verified and authorized to clean up:

1. Shift DNS away from the frontend per plan or confirm the lab hostname no longer needs to be served.
2. Delete the HTTPS forwarding rule (and HTTP redirect rule if created).
3. Delete the target HTTPS proxy and any lab-specific target proxies.
4. Delete the SSL certificate used only by the lab.
5. Delete the lab-only URL map.
6. Delete the load balancer backend bucket.
7. Release the global static IP once no forwarding rule references it.
8. Delete temporary objects, then delete the Cloud Storage bucket after verifying ownership, retention, and backups.
9. Remove dedicated test build triggers/role bindings if no longer needed.
10. Check Billing and resource inventory to confirm no unexpected billable resources remain.

Example frontend deletion **only after verifying exact names**:

~~~bash
gcloud compute forwarding-rules delete "$HTTPS_RULE" \
  --global \
  --project="$PROJECT_ID"

gcloud compute target-https-proxies delete "$HTTPS_PROXY" \
  --global \
  --project="$PROJECT_ID"

gcloud compute ssl-certificates delete "$TLS_CERT" \
  --global \
  --project="$PROJECT_ID"

gcloud compute url-maps delete "$URL_MAP" \
  --global \
  --project="$PROJECT_ID"

gcloud compute backend-buckets delete "$BACKEND_BUCKET" \
  --project="$PROJECT_ID"

gcloud compute addresses delete "$IP_NAME" \
  --global \
  --project="$PROJECT_ID"
~~~

**Warning:** Delete commands permanently destroy resources; never run them while the website is actively serving users or when resources are shared. If a separate HTTP redirect frontend exists, remove its dependencies first. For buckets, review object inventory in the Console before deleting; never use wildcards to wipe entire projects/buckets without checking retention and ownership.

Do not treat stopping website visits as proof that cost is zero. Inspect remaining resources, since static IPs, load balancing components, object storage, and log retention can continue generating charges depending on usage terms.

## 19. Milestone-Based Hands-On Exercises

This section organizes the project into independently evaluable milestones. Execute them in your lab project and capture screenshots/metrics as evidence, **without putting credentials or sensitive data into reports**.

### Milestone A — Working Static Website

1. Create the `site` folder with `index.html`, `about/index.html`, `404.html`, CSS, and JavaScript.
2. Open the website using a local development server and test all links.
3. Use DevTools to confirm CSS/JS report no MIME or 404 errors.
4. Test layout on small screens and keyboard accessibility.
5. Record the source version and list of files to publish.

**Evidence:** Home page, subpage, and JavaScript button work; no critical console errors.

### Milestone B — Properly Configured Cloud Storage Origin

1. Verify project ID, budget, and bucket name.
2. Create the bucket with the chosen location and uniform bucket-level access.
3. Upload the exact contents of `site/`.
4. Configure index/error pages.
5. Check `Content-Type` and `Cache-Control`.
6. Enable public read access only on a bucket **approved to be public**, or use private bucket access if required by your organization.

**Evidence:** Bucket object list matches source manifest; website configuration is valid; no secrets in objects.

### Milestone C — Working HTTPS and CDN

1. Reserve a global external IPv4.
2. Create a backend bucket pointing to Cloud Storage and enable Cloud CDN.
3. Create a URL map with the default backend bucket.
4. Provision a Google-managed certificate for a real hostname.
5. Create the target HTTPS proxy and port 443 global forwarding rule.
6. Point the DNS A record to the IP address.
7. Wait for the certificate to become ACTIVE, then test HTTPS in a browser and `curl`.
8. Send several requests and observe CDN/cache metrics.

**Evidence:** `https://hostname/` loads successfully, certificate is valid, and backend bucket shows CDN enabled.

### Milestone D — Releasing a Second Version

1. Change a heading or paragraph in `index.html`.
2. Update at least one CSS/JS asset.
3. Upload assets first, then HTML.
4. Verify response content/headers after publishing.
5. If necessary, invalidate exact paths `/` and `/index.html`.
6. Record the release ID, timestamp, and cache verification steps.

**Evidence:** Users receive new content within the policy window; asset links have no errors.

### Milestone E — Automation and Rollback

1. Create `cloudbuild.yaml` and a service account granted bucket write access.
2. Run a build from a test commit.
3. Verify build logs include validate and publish steps.
4. Intentionally break an asset path in a test environment and confirm the smoke test catches it.
5. Restore the previous release's artifacts and update caches per policy.
6. Verify the website returns to the expected state.

**Evidence:** Build ID, PASS/FAIL output, and rollback report. Never intentionally break someone else's production website.

### Milestone F — Operations and Cleanup

1. Build a minimal dashboard for requests, errors, CDN, and cost.
2. Create a synthetic check for the HTTPS homepage.
3. Review the Billing breakdown and compare against estimates.
4. Record the resource inventory.
5. When the lab ends, clean up resources in dependency order.
6. Verify no unintended billable resources remain.

**Evidence:** End-of-project checklist and before/after cleanup resource inventory.

### Project Evaluation Rubric

| Criterion | Reference Weight | Passing Condition |
|---|---:|---|
| Website and file structure | 15% | HTML/CSS/JS and 404 are testable |
| Cloud Storage and permissions | 20% | Bucket in right project, accurate metadata and IAM |
| HTTPS/DNS | 20% | Hostname and certificate valid, responses verified |
| CDN and cache policy | 15% | CDN enabled, sensible TTLs, measured with evidence |
| CI/CD and rollback | 15% | Automated release and verified rollback path |
| Security, cost, observability | 15% | No leaked secrets, metrics present, budget/cleanup done |

Weights are self-study examples. Organizations may adjust them based on security, reproducibility, and operational priorities.

## 20. Project Extensions

Once the baseline works, try one or more extensions:

### Extension 1 — Public Website with Private Origin

Switch to private bucket access compatible with global external Application Load Balancer and Cloud CDN. Remove `allUsers`; verify the frontend still serves content while direct origin access is blocked. Carefully check cacheability and cache mode requirements for private bucket access.

### Extension 2 — HTTP to HTTPS Redirect

In the Load Balancing Console or via a redirect URL map configuration:

1. Create an additional HTTP port 80 frontend on the same IP.
2. Route HTTP with a URL redirect to HTTPS, preserving host/path/query per policy.
3. Verify a `301` or `308` response code per configuration.
4. Ensure no redirect loops or redirects to the wrong domain occur.
5. Enable HSTS only once all relevant hostnames serve valid HTTPS.

**Do not** use port 80 to serve the same content over plain HTTP if the goal is HTTPS-only.

### Extension 3 — Frontend Calling a Java/Spring API on Cloud Run

Keep the website on the backend bucket, while running dynamic APIs on Cloud Run with a dedicated identity and authentication/authorization protection. Use `api.example.com` or host/path rules on the load balancer. Check CORS across origins and never put backend secrets in JavaScript.

### Extension 4 — CI/CD with Hashed Assets

Add an npm build step to emit content-hashed assets and set long TTLs on assets while keeping HTML on short TTLs or revalidation. Then run consecutive deployments and a rollback to prove no broken references to deleted files occur.

### Extension 5 — IaC and Change Control

Define the bucket, backend bucket, IP, URL map, certificate, proxy, and forwarding rule in Terraform or a compatible IaC tool. Protect state, review plans, and use a dedicated provisioning identity. Never run destroy on production resources just to test a lab change.

## 21. Pre-Completion Checklist

- [ ] Lab project and Billing verified.
- [ ] Budget alert and cost owner assigned.
- [ ] Real domain owned or authorized for use.
- [ ] Static website runs locally and contains no secrets.
- [ ] Bucket has a unique name, right location, and UBLA.
- [ ] Correct `index.html`, subpage, `404.html`, and assets uploaded.
- [ ] `Content-Type` accurate for HTML/CSS/JS/images.
- [ ] Website main page and not-found page configured.
- [ ] IAM grants public access only on approved content.
- [ ] Public access prevention policies respected.
- [ ] Public origin vs. private bucket access evaluated.
- [ ] Global IP, backend bucket, and URL map created in the right project.
- [ ] Cloud CDN enabled with an intentional cache policy.
- [ ] TLS certificate ACTIVE and matches hostname.
- [ ] DNS A record points to the right frontend IP.
- [ ] HTTPS root, about, and assets pass smoke tests.
- [ ] Verified 404 or corresponding error response for missing files.
- [ ] Short HTML cache; hashed assets (if used) have appropriate TTLs.
- [ ] Targeted invalidation or versioned-filename publishing in place.
- [ ] Cloud Build uses an identity with only required upload permissions.
- [ ] Builds/releases tagged with commit ID and rollback path ready.
- [ ] Checked mobile layout and keyboard navigation.
- [ ] Checked logs/metrics and configured basic alerts.
- [ ] Reviewed LB/CDN/Storage costs after testing phase.
- [ ] Lab-specific cleanup doc and resource inventory maintained.

## Self-Check Questions

**1. Why is Cloud Storage alone insufficient to serve a custom-domain website over HTTPS in this lesson's architecture?**

Because the website requires an HTTPS frontend with a certificate bound to the domain name. The Application Load Balancer terminates HTTPS and uses a URL map and backend bucket to fetch content from Cloud Storage.

**2. How does a backend bucket differ from a Cloud Storage bucket?**

A Cloud Storage bucket actually holds the objects. A backend bucket is a Load Balancing resource that references the Cloud Storage bucket and can attach a Cloud CDN policy.

**3. Why must a bucket granted `roles/storage.objectViewer` to `allUsers` contain only public content?**

Because anyone on the Internet can read objects and may list object metadata/filenames under the granted permission. A CDN does not make files in a public bucket secret.

**4. What does Uniform bucket-level access help with?**

It uses bucket-level IAM instead of object ACLs to control access and makes permission management more consistent.

**5. Does a certificate status of provisioning mean the HTTPS website is ready?**

No. You must wait for domain validation and issuance, check DNS, and confirm the certificate is ACTIVE/valid before publishing.

**6. Why shouldn't `index.html` be cached as `immutable` for one year when its filename does not change?**

Because browsers and CDNs can hold onto stale HTML even after a new version is published; users may miss updates or receive links to assets that are no longer valid.

**7. How do content-hashed assets help with long caching?**

When content changes, the filename/URL changes as well. Caches for old and new files never collide, enabling long TTLs while still shipping new releases cleanly.

**8. Does an invalidation command update objects in Cloud Storage?**

No. It instructs the CDN to stop serving matching cached responses. Source objects must be uploaded/updated separately.

**9. Why upload assets before HTML?**

Because new HTML may reference new assets. Publishing HTML before those assets exist can cause 404 errors or broken UI for users.

**10. When is private bucket access needed?**

When you want content served through a load balancer/CDN without allowing direct access to the origin via public bucket permissions. Permissions and caching must follow the supported model.

**11. Why should Cloud Build only have object write permissions instead of Owner?**

Because publishing only needs to update files in the bucket. Project-wide admin permissions widen the blast radius if build config or source code is compromised.

**12. Is a website with zero traffic guaranteed to incur zero cost?**

No. Load balancers, IPs, storage, and certain existing resources can continue generating charges. Always check resource inventory and Billing.

## References

- [Cloud Storage — Host a static website](https://docs.cloud.google.com/storage/docs/hosting-static-website)
- [Cloud Storage — Static website examples and tips](https://docs.cloud.google.com/storage/docs/static-website)
- [Cloud Load Balancing — Global external Application Load Balancer with Cloud Storage buckets](https://docs.cloud.google.com/load-balancing/docs/https/setup-global-ext-https-buckets)
- [Cloud Load Balancing — Backend buckets overview](https://docs.cloud.google.com/load-balancing/docs/backend-bucket)
- [Cloud CDN — Set up a backend bucket](https://docs.cloud.google.com/cdn/docs/setting-up-cdn-with-bucket)
- [Cloud CDN — Caching overview](https://docs.cloud.google.com/cdn/docs/caching)
- [Cloud CDN — Invalidate cached content](https://docs.cloud.google.com/cdn/docs/invalidating-cached-content)
- [Cloud Storage — Uniform bucket-level access](https://docs.cloud.google.com/storage/docs/uniform-bucket-level-access)
- [Cloud Storage — Public access prevention](https://docs.cloud.google.com/storage/docs/public-access-prevention)
- [Cloud CDN — Configure private bucket access](https://docs.cloud.google.com/cdn/docs/configure-private-bucket-access)
- [Google Cloud SDK — gcloud storage objects update](https://docs.cloud.google.com/sdk/gcloud/reference/storage/objects/update)
- [Google Cloud SDK — gcloud compute url-maps invalidate-cdn-cache](https://docs.cloud.google.com/sdk/gcloud/reference/compute/url-maps/invalidate-cdn-cache)
- [Google Cloud — Cloud Build documentation](https://docs.cloud.google.com/build/docs/overview)
- [Google Cloud — Pricing Calculator](https://cloud.google.com/products/calculator)

## Conclusion

A complete static website on GCP is more than HTML files uploaded to a bucket. **Cloud Storage** provides the content origin, **Application Load Balancer** provides the HTTPS frontend for a custom domain, a **Google-managed certificate** secures TLS connections, and **Cloud CDN** distributes content according to your cache policy. DNS routes users to the right frontend; IAM and public/private bucket access govern origin security; Cloud Build and release manifests keep updates traceable.

For production, the most important practice is clear separation: **only genuinely public content should be public**, HTML and assets should have tailored TTLs, publish permissions should be restricted, certificates/DNS should be monitored, and a rollback path should always exist. Combined with cost estimation, synthetic checks, and controlled cleanup, you have a complete hands-on project spanning website creation, release, and operations on Google Cloud.
