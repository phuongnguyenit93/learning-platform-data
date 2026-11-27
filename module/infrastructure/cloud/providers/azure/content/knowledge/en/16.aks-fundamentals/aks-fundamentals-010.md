# Ingress, Gateway API, and Exposing Applications on AKS

> **Chapter:** Azure Kubernetes Service Fundamentals  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Exploring the Microsoft Azure ecosystem from subscriptions, resource groups, and Entra ID to virtual networking, compute, storage, and data. Learn how to deploy, monitor, protect, and control costs for application architectures on Azure.

## Lesson objectives

After completing this lesson, you can:

1. Explain how requests from the Internet or a private network travel through **Azure Kubernetes Service (AKS)** to Pods.
2. Distinguish `ClusterIP`, `NodePort`, `LoadBalancer`, **Ingress**, and **Gateway API**.
3. Identify the roles of **Ingress controller**, **Gateway API controller**, `IngressClass`, and `GatewayClass`, understanding that declaring API resources alone does not create an entry path.
4. Deploy two test applications and expose them via **Ingress** with host/path routing and TLS certificates.
5. Describe and author **Gateway** and **HTTPRoute** manifests, and read route attachment status and conditions such as `Accepted`, `ResolvedRefs`, and `Programmed`.
6. Choose among **AKS application routing**, suitable Ingress controllers, **Azure Application Gateway**, or **Application Gateway for Containers** based on architecture and supportability.
7. Troubleshoot DNS, TLS, HTTP 404/502/503, Service endpoints, health probes, ingress controllers, and configuration permissions.
8. Design security, monitoring, rollouts, autoscaling, and cost control when publishing workloads on AKS.

## 1. The problem: exposing in-cluster applications to users

Suppose an enterprise deploys two microservices on AKS:

- `catalog`: product listing API listening on port `5678`.
- `orders`: order processing API also listening on port `5678`.

Externally, users only want to visit a single domain:

~~~text
https://shop.example.com/catalog
https://shop.example.com/orders
~~~

Inside the cluster, applications run as **Pods**; Pods can be replaced, change IPs, or scale replicas. You cannot point public DNS directly at a Pod IP and expect stability.

One way to organize this:

~~~mermaid
flowchart LR
    U["Internet Client"]
    DNS["DNS shop.example.com"]
    LB["Public IP / Azure Load Balancer\nor L7 gateway"]
    IC["Ingress/Gateway controller\nHTTP routing point"]
    S1["Service catalog-svc"]
    S2["Service orders-svc"]
    P1["catalog Pods"]
    P2["orders Pods"]
    U --> DNS --> LB --> IC
    IC -->|"/catalog"| S1 --> P1
    IC -->|"/orders"| S2 --> P2
~~~

This diagram illustrates the **logical flow**. In some Azure-managed L7 solutions, the controller inside Kubernetes only **reconciles configuration**, while data traffic traverses an external gateway outside cluster nodes rather than a proxy pod inside the cluster. Always check the chosen product's data plane.

**Goal:** publish a stable domain name, route by HTTP host/path, manage TLS, and decouple clients from individual Pod IPs.

## 2. Kubernetes objects along the request path

### 2.1. Pod and Deployment

- **Pod** is the execution unit running one or more containers sharing a network namespace.
- **Deployment** manages replica counts and rollouts for stateless Pods.
- A Pod gets an IP inside the cluster network; this IP can change whenever the Pod is recreated.

For example, Deployment `catalog` has 2 replicas, each potentially receiving a different address. End users should never need to know those addresses.

### 2.2. Service and Service types

**Service** creates a stable access point to selected Pods via `selector` and `ports`.

| `Service.type` | Usage scope | When to use |
| --- | --- | --- |
| `ClusterIP` | In-cluster internal entry point | Backend behind Ingress/Gateway or internal microservice communication |
| `NodePort` | Opens a port on every node per Kubernetes config | Specific connectivity or specialized setups; rarely the best default for public web |
| `LoadBalancer` | Requests cloud integration to provision an external load balancer | Exposing TCP/UDP or a single service directly; public or internal per config |
| `ExternalName` | Maps service name to another DNS name | Service discovery to external services where supported; creates no proxy |

On AKS, a standard `Service.type=LoadBalancer` may prompt the platform to provision an Azure Load Balancer and frontend address per config. Without an internal mode annotation/setting, it **may expose to the Internet**; verify policies and actual resources.

**ClusterIP** cannot be reached directly from the Internet. It is the right type for backend Services behind Ingress or Gateway.

### 2.3. Where do Ingress and Gateway API sit?

- **Ingress** is a Kubernetes API for Layer 7 **HTTP/HTTPS routing**, supporting host/path rules and TLS per controller capabilities.
- **Gateway API** is a family of Kubernetes APIs expressing clear roles, listeners, routes, and route-to-gateway attachment with a richer extensibility model.
- **Ingress controller / Gateway controller** is the component that **implements the configuration**: programming proxies/gateways, selecting backends, configuring the data plane, and reporting status.
- **Azure Load Balancer** operates primarily at Layer 4; it cannot read an `Ingress` manifest and route by URL path without a suitable Layer 7 controller.

Do not confuse **Kubernetes Gateway API** with a business API management gateway such as Azure API Management. Both can coexist in an architecture, serving different functions and audiences.

### 2.4. Architectural layering

~~~mermaid
flowchart TD
    C["Client"]
    D["DNS + public/private endpoint"]
    T["TLS listener / HTTP routing"]
    R["Ingress or Gateway + HTTPRoute"]
    S["Kubernetes Service"]
    E["EndpointSlices"]
    P["Ready Pods"]
    C --> D --> T
    R -.->|"Controller reconcile"| T
    T --> S --> E --> P
~~~

`EndpointSlice` stores backend endpoint information for a Service, updated based on Pods and readiness state. If a Service has a wrong selector or Pods are not Ready, the controller has no usable backends even when Ingress/Gateway manifests are completely valid.

## 3. Four common ways to expose applications on AKS

| Approach | Primary entry point | HTTP host/path routing | Best fit |
| --- | --- | --- | --- |
| `Service.type=LoadBalancer` | Azure L4 load balancer | Does not provide L7 routing on its own | TCP/UDP services, single simple endpoint |
| **Ingress + controller** | Installed or Azure-managed Ingress controller | Yes, per Ingress API/controller | Multiple web APIs sharing one entry point |
| **Gateway API + controller** | Controller-managed Gateway data plane | Yes, via `HTTPRoute` and supported route types | Platform/app separation, advanced routing, multi-team models |
| **Edge service in front of AKS** | Azure Front Door, Application Gateway, WAF, or equivalent | Depends on product and connection tier | Global reach, edge protection, CDN, WAF, enterprise requirements |

**Key distinction:** creating a separate `Service.type=LoadBalancer` per application may look simple, yet multiplies public endpoints, certificates, and policies to manage. Ingress/Gateway consolidates many Services behind one or a few entry points.

### 3.1. When to use `LoadBalancer` directly?

A TCP or UDP application without HTTP path routing can use `LoadBalancer` directly. Example:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: tcp-service
  namespace: shop
spec:
  type: LoadBalancer
  selector:
    app: some-tcp-app
  ports:
    - name: tcp
      port: 443
      targetPort: 9443
      protocol: TCP
~~~

This is an **illustrative manifest** without a backend Deployment. On AKS, creating this Service may allocate a **public frontend IP** and incur charges. It also **does not perform TLS termination or HTTP path routing** simply because it listens on port 443.

To request an internal load balancer in a supported AKS model:

~~~yaml
metadata:
  annotations:
    service.beta.kubernetes.io/azure-load-balancer-internal: "true"
~~~

This annotation is an Azure cloud provider example; place it on the **Service's `metadata`**, verify networking/subnet/permissions, and confirm the Service receives a private IP. Never treat this annotation as an authentication control.

### 3.2. When should you choose Ingress/Gateway?

An application with multiple HTTP/HTTPS APIs requiring host/path routing, HTTPS redirects, and TLS certificates typically needs Layer 7 routing. Pick a production controller supported on your AKS/Kubernetes version with the features you need, rather than applying YAML and hoping an IP magically appears.

## 4. Preparation before deployment

### 4.1. Verify context and permissions

In these examples, commands run on an admin machine with `az` and `kubectl` and authorized cluster permissions.

~~~bash
az login
az account show \
  --query "{name:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

# Replace with your assigned subscription.
az account set --subscription "<SUBSCRIPTION_ID>"

RG="rg-aks-lab"
AKS="aks-web-lab"

# Update kubeconfig for the authorized cluster.
az aks get-credentials \
  --resource-group "$RG" \
  --name "$AKS"

kubectl config current-context
kubectl get nodes
kubectl get namespaces
~~~

**Note:** `az aks get-credentials` updates kubeconfig on your local machine. It does not install clusters, controllers, or grant Kubernetes RBAC to unauthorized accounts.

### 4.2. Verify controllers/CRDs upfront

Before using Ingress or Gateway API, check which resources actually exist:

~~~bash
kubectl get ingressclasses

kubectl get gatewayclasses.gateway.networking.k8s.io

kubectl api-resources | grep -E 'ingresses|gateways|httproutes'
~~~

If `GatewayClass` or `HTTPRoute` reports "resource type not found," the cluster probably **lacks Gateway API CRDs**. If CRDs exist without a running controller/GatewayClass, creating a `Gateway` will not pass traffic.

If an `IngressClass` exists, verify its backing controller is actually running; seeing a class name in the API does not prove the proxy is running or ready.

### 4.3. Lab safety boundaries

- Examples use the documentation domain `shop.example.com`, **not a DNS domain you own**. For real HTTPS, substitute your organization's domain and valid certificates.
- Both sample apps use simple public images solely to demonstrate routing, with zero production data.
- Never run `kubectl apply` on production clusters outside change-management processes.
- Never install a duplicate Ingress/Gateway controller alongside an existing cluster solution; doing so can spin up extra public load balancers or conflict over permissions.
- Never modify production role assignments, networking, public DNS, or production certificates just for practice.

## 5. Creating two backend Deployments and ClusterIP Services

### 5.1. Dedicated namespace for the lab

~~~bash
kubectl create namespace shop
~~~

If the namespace already exists, no need to recreate it. In production, apply RBAC, ResourceQuota, LimitRange, and NetworkPolicy before letting teams deploy workloads.

### 5.2. File `microservices.yaml`

The following example uses `hashicorp/http-echo` to return static text. In production, pin image digests, scan images, and use private registries. Both `/catalog` and `/orders` lab APIs simply return text to observe routing, not a real e-commerce backend.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog
  namespace: shop
spec:
  replicas: 2
  selector:
    matchLabels:
      app: catalog
  template:
    metadata:
      labels:
        app: catalog
    spec:
      containers:
        - name: echo
          image: hashicorp/http-echo:1.0.0
          args:
            - "-listen=:5678"
            - "-text=CATALOG service response"
          ports:
            - name: http
              containerPort: 5678
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              cpu: 250m
              memory: 128Mi
          readinessProbe:
            httpGet:
              path: /
              port: http
            initialDelaySeconds: 2
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: catalog-svc
  namespace: shop
spec:
  type: ClusterIP
  selector:
    app: catalog
  ports:
    - name: http
      port: 80
      targetPort: http
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
  namespace: shop
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders
  template:
    metadata:
      labels:
        app: orders
    spec:
      containers:
        - name: echo
          image: hashicorp/http-echo:1.0.0
          args:
            - "-listen=:5678"
            - "-text=ORDERS service response"
          ports:
            - name: http
              containerPort: 5678
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              cpu: 250m
              memory: 128Mi
          readinessProbe:
            httpGet:
              path: /
              port: http
            initialDelaySeconds: 2
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: orders-svc
  namespace: shop
spec:
  type: ClusterIP
  selector:
    app: orders
  ports:
    - name: http
      port: 80
      targetPort: http
~~~

**Port path explanation:** in-cluster clients call the Service on `port: 80`. The Service forwards to port `5678` on the Pod via `targetPort: http`, referencing the named container port `http`.

- `selector: app: catalog` must match the Pod labels of Deployment `catalog`.
- `readinessProbe` decides whether each Pod becomes a ready endpoint.
- `replicas: 2` is desired Pod count, not public load balancer count.
- Neither `ClusterIP` Service is **exposed to the Internet yet**.

### 5.3. Apply and verify before publishing

~~~bash
kubectl apply -f microservices.yaml

kubectl -n shop rollout status deployment/catalog
kubectl -n shop rollout status deployment/orders

kubectl -n shop get deployments,pods,services

kubectl -n shop get endpointslices \
  -l kubernetes.io/service-name=catalog-svc

kubectl -n shop get endpointslices \
  -l kubernetes.io/service-name=orders-svc
~~~

If a Service has no ready endpoints, stop here and inspect Pod labels, container logs, readiness probes, and image pulls before configuring Ingress/Gateway.

To test internal routing without a public endpoint, use `port-forward` in an authorized lab:

~~~bash
kubectl -n shop port-forward service/catalog-svc 8081:80

# In another terminal:
curl http://127.0.0.1:8081/
~~~

**Port-forward is only a temporary test tunnel to a Kubernetes Service**, not a production public publishing mechanism.

## 6. Exposing HTTP with Kubernetes Ingress

### 6.1. Ingress is a declaration; the controller performs routing

An Ingress manifest declares:

- `ingressClassName`: selects which Ingress controller processes it.
- `rules.host`: HTTP hostname.
- `http.paths`: path-based routing rules.
- `backend.service`: target Kubernetes Service and port.
- `tls`: HTTPS hostnames and reference to a TLS Secret in the same namespace per rules.

The controller can be an AKS-managed solution, an organization-operated controller, or an integration with an Azure L7 gateway. Controllers differ in **annotations, TLS features, rewrites, WAF, health checks, and lifecycles**; avoid blindly copying annotations from controller A to controller B.

### 6.2. Identify the real IngressClass

~~~bash
kubectl get ingressclass

kubectl describe ingressclass <INGRESS_CLASS_NAME>
~~~

**Replace** `<INGRESS_CLASS_NAME>` with the active class managed on your cluster. The manifest below uses `replace-with-installed-class` to avoid assuming a specific product's class. Replace it with a real class **before applying**.

### 6.3. File `ingress.yaml`

~~~yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: shop-ingress
  namespace: shop
spec:
  ingressClassName: replace-with-installed-class
  rules:
    - host: shop.example.com
      http:
        paths:
          - path: /catalog
            pathType: Prefix
            backend:
              service:
                name: catalog-svc
                port:
                  number: 80
          - path: /orders
            pathType: Prefix
            backend:
              service:
                name: orders-svc
                port:
                  number: 80
~~~

**Why does this example omit path rewrite?** Both `http-echo` backends reply with text on any path, letting us observe routing without rewrites. For real APIs accepting only `/` or `/v1/*`, design application paths accordingly or configure rewrites **specific to your controller**. The standard Ingress API does not standardize rewrites or advanced routing into common fields.

Once the class name is updated, apply:

~~~bash
kubectl apply -f ingress.yaml

kubectl -n shop get ingress
kubectl -n shop describe ingress shop-ingress
~~~

Check the `ADDRESS` column and events. If a controller exists yet no address appears or Ingress status isn't ready, public DNS will not work yet.

### 6.4. Test host routing before configuring DNS

If the Ingress controller already has an **approved public IP for testing**, send requests with a `Host` header before creating DNS records:

~~~bash
# IP 203.0.113.10 is illustrative only; substitute the real endpoint.
curl -i \
  -H "Host: shop.example.com" \
  http://203.0.113.10/catalog

curl -i \
  -H "Host: shop.example.com" \
  http://203.0.113.10/orders
~~~

Expected responses: `CATALOG service response` and `ORDERS service response`. IP `203.0.113.10` is a **documentation-reserved address**, not an actual cluster IP.

If the controller returns 404, check hostname/path matching, IngressClass, and rules. If it returns 503/502, check backend Service endpoints, Pod readiness, and controller logs.


## 7. HTTPS, DNS, and certificate management for Ingress

### 7.1. From ingress IP to a real hostname

For an organization-managed domain, you typically need:

1. A stable **frontend endpoint** on the controller/gateway per your deployment model.
2. A DNS record such as an **A** record pointing `shop.example.com` to the public IP, or a CNAME per service/architecture requirements.
3. A TLS certificate with a SAN covering `shop.example.com`.
4. Attaching the certificate to the controller's listener/Ingress.
5. Testing the TLS handshake, HTTP path routing, and backend requests.

**A DNS record does not create an ingress controller.** Conversely, creating an Ingress does not automatically create DNS records. Some setups use ExternalDNS or DNS integrations to automate record updates, which require separate DNS permissions and configuration.

### 7.2. TLS Secret for Ingress

If the controller supports Ingress TLS via Kubernetes Secrets, store the certificate and private key as a `kubernetes.io/tls` Secret **in the same namespace as the Ingress**, e.g., `shop`.

Illustrative command using an organization-issued certificate:

~~~bash
# Use only valid certificates/keys owned by your organization.
# Never put private keys in source code or commit them to Git.
kubectl -n shop create secret tls shop-tls \
  --cert=/secure/certs/shop-fullchain.pem \
  --key=/secure/certs/shop-private.key
~~~

Note: **a Kubernetes Secret is not encrypted end-to-end by default simply because it is called "Secret."** Enforce RBAC, encryption at rest per cluster capability, secure certificate distribution, and rotation processes. Consider **cert-manager** or Azure Key Vault / CSI / certificate management integrations where supported by the controller.

### 7.3. Adding `tls` to Ingress

An HTTPS variant `ingress-https.yaml` of the Ingress from section 6:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: shop-ingress
  namespace: shop
spec:
  ingressClassName: replace-with-installed-class
  tls:
    - hosts:
        - shop.example.com
      secretName: shop-tls
  rules:
    - host: shop.example.com
      http:
        paths:
          - path: /catalog
            pathType: Prefix
            backend:
              service:
                name: catalog-svc
                port:
                  number: 80
          - path: /orders
            pathType: Prefix
            backend:
              service:
                name: orders-svc
                port:
                  number: 80
~~~

Apply after replacing IngressClass and preparing the TLS Secret:

~~~bash
kubectl apply -f ingress-https.yaml
kubectl -n shop describe ingress shop-ingress
kubectl -n shop get secret shop-tls
~~~

The Secret holds sensitive key material. **Never print or paste `data.tls.key` contents into chats or logs** for a "quick check"; inspect only Secret metadata, public chains, or test the handshake against the endpoint.

### 7.4. TLS termination vs. backend encryption

A common pattern:

~~~text
Client --HTTPS--> Ingress controller --HTTP--> catalog-svc --> Pods
~~~

TLS terminates at the ingress controller. That **does not mean traffic from ingress to Pods uses HTTPS**. If internal encryption is required, configure backend TLS protocols, a service mesh/mTLS, or an appropriate gateway feature per controller support; the core Ingress API does not unify backend TLS behavior into a single standard field.

### 7.5. Redirecting HTTP to HTTPS

Not every controller redirects HTTP to HTTPS the same way by default. Some enable it out of the box, while others require annotations or policies. Before claiming "HTTP is blocked/redirected," verify:

~~~bash
curl -I http://shop.example.com/catalog
curl -I https://shop.example.com/catalog
~~~

In production, TLS certificates must be valid. **Never use `curl -k` as proof that TLS is compliant**: `-k` disables client certificate verification.

If DNS isn't updated yet and you want to test HTTPS against an already provisioned frontend IP:

~~~bash
# IP 203.0.113.10 is an example; substitute the real frontend IP.
curl -v \
  --resolve shop.example.com:443:203.0.113.10 \
  https://shop.example.com/catalog
~~~

`--resolve` preserves the hostname for TLS SNI and HTTP `Host` while forcing TCP to the specified IP—ideal for validating certificates and routing before DNS cutover.

## 8. Gateway API: the modern model for governing L7 connectivity

**Gateway API** is a set of Kubernetes APIs developed by the Kubernetes community to model routing and operational roles more cleanly. It is not a proxy itself; it still requires a compatible **implementation/controller**.

### 8.1. Four key objects

| Object | Typical owner | Responsibility |
| --- | --- | --- |
| `GatewayClass` | Platform/network team | Selects the implementation/controller and platform parameters |
| `Gateway` | Infra/cluster operator | Defines listeners, ports, protocols, hostnames, TLS, and allowed route scopes |
| `HTTPRoute` | App/team owner | Match rules by host/path/headers and `backendRefs` |
| `ReferenceGrant` | Owner of namespace holding target resource | Permits cross-namespace references, e.g., an HTTPRoute `backendRef` to a Service in another namespace |

Conceptual view:

~~~mermaid
flowchart TD
    CLASS["GatewayClass\nplatform controller"]
    G["Gateway\nlisteners :80/:443"]
    R1["HTTPRoute team-catalog\n/catalog"]
    R2["HTTPRoute team-orders\n/orders"]
    S1["catalog-svc"]
    S2["orders-svc"]
    CLASS --> G
    R1 -->|"parentRefs"| G
    R2 -->|"parentRefs"| G
    R1 -->|"backendRefs"| S1
    R2 -->|"backendRefs"| S2
~~~

Gateway/HTTPRoute separates ownership of the **entry point** from ownership of **application routes**—a major advantage when multiple teams share publishing infrastructure.

### 8.2. GatewayClass provided by the controller

Check installed classes:

~~~bash
kubectl get gatewayclass
kubectl describe gatewayclass <GATEWAY_CLASS_NAME>
~~~

`GatewayClass` contains `controllerName` pointing to the implementation. Class names and controllers **are not automatically generated by Kubernetes on every cluster**. Pick a class matching what your organization installed, such as an Azure gateway controller or another supported implementation.

If Gateway API CRDs are not installed, do not apply the YAML below yet; install CRDs/controllers with proper version governance first.

### 8.3. Minimal HTTP Gateway and HTTPRoute

Example `gateway-http.yaml`. **Replace** `replace-with-installed-class` with a real GatewayClass:

~~~yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: shop-gateway
  namespace: shop
spec:
  gatewayClassName: replace-with-installed-class
  listeners:
    - name: web
      protocol: HTTP
      port: 80
      hostname: shop.example.com
      allowedRoutes:
        namespaces:
          from: Same
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: shop-routes
  namespace: shop
spec:
  parentRefs:
    - name: shop-gateway
      sectionName: web
  hostnames:
    - shop.example.com
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /catalog
      backendRefs:
        - name: catalog-svc
          port: 80
    - matches:
        - path:
            type: PathPrefix
            value: /orders
      backendRefs:
        - name: orders-svc
          port: 80
~~~

Path mapping:

~~~text
HTTPRoute(shop-routes)
  parentRefs  → Gateway(shop-gateway), listener web :80
  /catalog    → Service catalog-svc:80
  /orders     → Service orders-svc:80
~~~

**Prerequisites:** the implementation/controller must support Gateway API `v1` with `Gateway` + `HTTPRoute`, a valid `GatewayClass`, and data-plane listener programming. YAML alone creates no public IP.

### 8.4. Apply and verify status

~~~bash
kubectl apply -f gateway-http.yaml

kubectl -n shop get gateways.gateway.networking.k8s.io
kubectl -n shop get httproutes.gateway.networking.k8s.io

kubectl -n shop describe gateway shop-gateway
kubectl -n shop describe httproute shop-routes

kubectl -n shop get gateway shop-gateway -o yaml
kubectl -n shop get httproute shop-routes -o yaml
~~~

Inspect these status groups:

- `Gateway.status.addresses`: endpoint assigned per controller model.
- Listeners and `status.conditions`: whether accepted and programmed cleanly.
- `HTTPRoute.status.parents` and `conditions`: whether the route was accepted by the Gateway and all references resolved.
- `GatewayClass.status.conditions`: whether the class is accepted by the controller.

Common conditions:

| Condition | Observed meaning | What to check when `False` |
| --- | --- | --- |
| `Accepted` | Gateway/route accepted by implementation per constraints | Listener, hostname, class, `allowedRoutes` |
| `ResolvedRefs` | Backends/Secrets and references resolved validly | Service name, port, namespace, `ReferenceGrant` |
| `Programmed` | Gateway/listener programmed into the data plane by controller | Endpoint/IP, cloud resource provisioning, permissions, controller logs |

Condition names and meanings must be read **against the specific resource and implementation**. Never stop at checking that an HTTPRoute exists; it can exist in the API server while **rejected by the controller**.

## 9. Gateway API with HTTPS and advanced routing

### 9.1. HTTPS listener and certificate

A Gateway configured with an HTTPS listener:

~~~yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: shop-gateway
  namespace: shop
spec:
  gatewayClassName: replace-with-installed-class
  listeners:
    - name: https
      protocol: HTTPS
      port: 443
      hostname: shop.example.com
      tls:
        mode: Terminate
        certificateRefs:
          - kind: Secret
            name: shop-tls
      allowedRoutes:
        namespaces:
          from: Same
~~~

The `shop-tls` resource in this example lives **in the same `shop` namespace as the Gateway**. The certificate must include a matching SAN for the hostname and a valid private key. Some implementations offer alternative certificate integrations; check your GatewayClass/controller's feature support rather than assuming every backend consumes Secrets identically.

HTTPRoute attaching to the `https` listener:

~~~yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: shop-routes
  namespace: shop
spec:
  parentRefs:
    - name: shop-gateway
      sectionName: https
  hostnames:
    - shop.example.com
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /catalog
      backendRefs:
        - name: catalog-svc
          port: 80
    - matches:
        - path:
            type: PathPrefix
            value: /orders
      backendRefs:
        - name: orders-svc
          port: 80
~~~

**Application note:** this HTTPS example **replaces** the HTTP `shop-gateway` configuration from section 8. Running `kubectl apply` against the same Gateway name will **update** its listeners. To keep both HTTP and HTTPS active, declare both listeners inside **the same Gateway manifest** with matching routes/HTTPRoutes.

### 9.2. HTTP → HTTPS redirect

Gateway API `HTTPRoute` defines standard filters including `RequestRedirect` where supported. With an existing HTTP listener named `web`, a redirect route looks like:

~~~yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: shop-redirect
  namespace: shop
spec:
  parentRefs:
    - name: shop-gateway
      sectionName: web
  hostnames:
    - shop.example.com
  rules:
    - filters:
        - type: RequestRedirect
          requestRedirect:
            scheme: https
            statusCode: 301
~~~

For this to work, the Gateway must have both an **HTTP `:80` `web` listener** and an **HTTPS `:443` listener**, and the implementation must support `RequestRedirect`. Never apply the redirect route without the `web` listener. Verify HTTP 301 and the `Location` header from a client.

### 9.3. Weighted routing across multiple Services

Some Gateway API implementations support weighted routing for canary releases:

~~~yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: catalog-canary
  namespace: shop
spec:
  parentRefs:
    - name: shop-gateway
      sectionName: https
  hostnames:
    - shop.example.com
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /catalog
      backendRefs:
        - name: catalog-stable-svc
          port: 80
          weight: 90
        - name: catalog-canary-svc
          port: 80
          weight: 10
~~~

**Illustrative canary manifest only**: Services `catalog-stable-svc` and `catalog-canary-svc` **must be created separately**; they are not included in the section 5 lab Deployment. When using canary routes, avoid another HTTPRoute with identical matches that conflicts or alters controller precedence.

The `90/10` weight is a statistical distribution target, not a strict guarantee that every 10th request hits canary. Small sample sizes, sessions, or caching can skew observed ratios.

### 9.4. Header matching, URL rewrite, and filters

Gateway API can express matches and filters such as:

- Matching on hostname, path, headers, and query parameters where supported.
- HTTP-to-HTTPS redirects.
- Header modification.
- URL rewrites when supported by the implementation.
- Weighted `backendRefs`.

**Not every controller supports every standard feature and extension.** Before adopting a filter or route kind, check the implementation's Gateway API conformance/feature matrix for your running version, and verify status conditions after deploying.

## 10. Multiple namespaces: governing routes and backends

### 10.1. Pattern: platform team owns Gateway, app teams own HTTPRoutes

An organization can structure namespaces as:

~~~text
namespace: network-system
  Gateway: shared-gateway

namespace: team-catalog
  HTTPRoute: catalog-route
  Service: catalog-svc

namespace: team-orders
  HTTPRoute: orders-route
  Service: orders-svc
~~~

The platform-operated Gateway permits HTTPRoutes from selected namespaces via `listeners[].allowedRoutes`. Each app team manages its authorized paths within organizational bounds.

Example Gateway listener permitting routes only from namespaces labeled `expose=approved`:

~~~yaml
listeners:
  - name: https
    protocol: HTTPS
    port: 443
    hostname: shop.example.com
    tls:
      certificateRefs:
        - name: shop-tls
    allowedRoutes:
      namespaces:
        from: Selector
        selector:
          matchLabels:
            expose: approved
~~~

This is a **listener YAML snippet** for illustration, not a complete Gateway manifest. Namespace labels act as route-attachment policy; control who can label namespaces. Under default `from: Same`, HTTPRoutes in other namespaces **do not attach**, even when route creation succeeds.

### 10.2. `ReferenceGrant` and cross-namespace `backendRefs`

Suppose an HTTPRoute in `team-catalog` wants to target a Service in `shared-backend`. Under Gateway API, certain cross-namespace references require a **`ReferenceGrant`** created by the owner of the **target resource's namespace** permitting the referrer.

Distinguish clearly:

- **HTTPRoute in another namespace attaching to a Gateway:** governed by listener `allowedRoutes` and `parentRefs`.
- **HTTPRoute referencing a Service in another namespace:** requires a cross-namespace reference permission, typically a `ReferenceGrant` in the Service's namespace.
- A Gateway listener referencing a TLS Secret in another namespace may also enforce reference/permission constraints.

Never assume creating a `ReferenceGrant` bypasses `allowedRoutes`, or that `allowedRoutes` automatically permits cross-namespace `backendRefs`.

### 10.3. RBAC and shared governance

- Platform team manages `GatewayClass`, Gateways, external IPs, TLS, and network/WAF controls.
- Application teams manage `HTTPRoute`/Ingress and Services within their own namespaces.
- DNS edits and certificate issuance follow dedicated approval workflows.
- If teams can create HTTPRoutes with sensitive hostnames/paths, add admission policies and peer reviews.

Never let arbitrary namespaces claim `shop.example.com` on a shared Gateway without ownership rules, preventing routing conflicts and security risks.

## 11. Common ingress/gateway options on AKS

### 11.1. AKS application routing

AKS offers an **application routing** capability to simplify configuring an Ingress controller in supported features and regions. Where supported, it is a convenient option for deploying **Ingress API** workloads over HTTP/HTTPS without self-managing the entire routing stack.

Verify in your live environment:

- AKS/Kubernetes version and add-on support at deployment time.
- Exact `IngressClass` name and whether controller pods are healthy.
- External/internal ingress mode and network/subnet configuration.
- How DNS, certificates, and HTTPS are managed.
- Lifecycle, maintenance policy, and security support of the underlying controller.

Example AKS status check:

~~~bash
az aks show \
  --resource-group "$RG" \
  --name "$AKS" \
  --query "{name:name, ingressProfile:ingressProfile}" \
  --output json

kubectl get ingressclass
~~~

If not yet enabled, never run enable commands in production without assessing impact, cost, IP allocation, and compatibility with existing controllers.

**Note:** NGINX controllers and specific implementations evolve in lifecycle and support policies across versions. Do not follow legacy installation tutorials for unmaintained controllers merely because they were popular in older blogs. For new systems, evaluate options currently supported by AKS and the vendor.

### 11.2. Application Gateway Ingress Controller (AGIC)

**AGIC** is an integration/controller that reads **Kubernetes Ingress** configs to program **Azure Application Gateway** in supported models and versions.

Conceptual flow:

~~~mermaid
flowchart LR
    I["Kubernetes Ingress"]
    AGIC["AGIC controller\nreconciles config"]
    AGW["Azure Application Gateway\nL7 data plane"]
    S["Kubernetes Service"]
    P["AKS Pods"]
    I -.-> AGIC -.-> AGW
    AGW --> S --> P
~~~

In this model, Application Gateway is the L7 resource sitting in front of the cluster; the controller itself is not necessarily an HTTP proxy in the data path.

Items to verify: Application Gateway SKU/tier, AGIC integration mode, VNet/peering/routing, backend health probes, TLS, WAF, identity/permissions, and product version capabilities.

### 11.3. Application Gateway for Containers

**Azure Application Gateway for Containers** uses its own data plane architecture and ALB Controller, supporting Kubernetes Gateway API and Ingress per specific features and versions. It is **not the same Azure resource** as traditional Azure Application Gateway paired with AGIC.

This option is worth evaluating when your organization needs an Azure-managed L7 gateway deeply integrated with AKS, Gateway API routing, and modern data-plane capabilities where supported.

Verify:

- Matching controller and `GatewayClass` actually exist in the cluster.
- Gateway API features/CRD versions supported by the implementation.
- Resource/region and networking prerequisites.
- Ownership model for ALB, frontends, TLS, traffic, and permissions.
- Dedicated logging, health probes, security policies, and billing.

Never reuse manifests containing controller A's `gatewayClassName` for controller B without verification. `GatewayClass` names are **implementation-specific**.

### 11.4. Azure Front Door and API Management do not replace in-cluster controllers

- **Azure Front Door** provides global entry points, routing/caching, and WAF per tier/config. It forwards traffic to a published AKS origin, yet **does not create Service endpoints inside the cluster**.
- **Azure API Management** focuses on API governance, policies, subscriptions, authentication, and developer portals. It can sit in front of AKS, yet is not a Kubernetes `GatewayClass` by default.
- **Azure Load Balancer** provides public/private L4 frontends for an ingress controller or Service, yet does not interpret `HTTPRoute` rules.
- **Application Gateway** and **Application Gateway for Containers** are separate L7 products with distinct data planes and controller integrations.

An architecture may chain **Front Door → WAF/gateway → AKS Service → Pods**; each layer must be configured and monitored independently. Avoid leaving backends directly open to the Internet where callers could bypass WAF.


## 12. Public vs. private publishing: choosing the right network boundary

### 12.1. Public ingress

If a site serves external Internet users, the ingress/gateway uses a public frontend IP or public L7 endpoint. Key configurations to review:

1. **DNS** pointing to the right frontend IP/hostname.
2. **TLS** with valid certificates, hostnames, and HTTP/HTTPS redirect policy.
3. **Ingress/Gateway controller** healthy and actively programming routes.
4. **Data plane to Service/Pod** properly routed and permitted.
5. **NSGs/firewalls/network policies** accurately scoped.
6. **Authentication, WAF/rate limiting** when L7 protection is required.
7. **Observability** for errors, latency, certificate expiration, and backend health.

Avoid creating a public `Service.type=LoadBalancer` for every backend simply because it feels quick. One gateway can consolidate multiple APIs behind a single ingress point, reducing public attack surfaces and centralizing policies.

### 12.2. Private ingress

Applications for employees over VPN/ExpressRoute or VNet workloads can use a **private IP frontend / internal ingress**.

~~~text
On-premises machine -- VPN/ExpressRoute -- VNet/private DNS
                                            |
                                            v
                                    Internal gateway :443
                                            |
                                            v
                                    Service → Ready Pods
~~~

Verify:

- Is the private IP routable from target clients?
- Does the Private DNS Zone / forwarding resolve the hostname?
- Do network security rules permit the right ports and sources?
- Does the TLS certificate include SANs matching internal hostnames?
- Does the gateway/controller support private frontends as configured?
- Are users authenticated and authorized?

**Private AKS cluster** describes access to the **Kubernetes API server / control plane**; it **does not automatically make every Service or Ingress private**. Likewise, an AKS cluster with a public API server can still serve apps over private ingress.

### 12.3. Entry-path decision table

| Question | Design impact |
| --- | --- |
| Internet or internal clients? | Public/private endpoint, DNS, and firewalls |
| Need HTTP host/path or TCP/UDP? | Ingress/Gateway API vs. L4 Service LoadBalancer |
| Multiple teams sharing one entry point? | Gateway API, `allowedRoutes`, and RBAC |
| Need WAF, CDN, multi-region? | Azure Front Door or suitable L7 gateway |
| Who manages DNS and TLS? | Static IP/hostname, certificates/Key Vault, and rotation |
| Where does TLS terminate? | Frontend cert, backend TLS, mTLS if required |
| Are backends protected from bypass? | Prevent unintended public LBs |
| Do Dev/Prod need isolation? | Namespaces, clusters, gateways, policies, and identities |

### 12.4. Risk of two public paths to the same backend

Suppose an API sits behind Front Door/WAF yet also keeps a direct public `LoadBalancer` Service open. Callers can hit the backend directly and **bypass edge WAF, rate limiting, or authentication**.

Regularly inventory public IPs, `Service.type=LoadBalancer`, Ingresses, Gateways, origin endpoints, and routing policies. Every public path needs an owner, a documented justification, and monitoring.

## 13. Health checks and Service endpoints

### 13.1. Readiness, liveness, and gateway health differ

- **Readiness probe:** decides if a Pod can receive traffic via Service.
- **Liveness probe:** decides if a container must be restarted.
- **Startup probe:** gives slow-starting apps boot time before other probes run.
- **Gateway/backend health check:** separate mechanism run by the controller or L7 gateway to probe upstreams.

They are not automatically synchronized in semantics. A Pod can be Ready while Application Gateway marks the backend `Unhealthy` because the gateway probe hits the wrong hostname, port, path, or rejects a backend TLS certificate.

### 13.2. From Pod readiness to EndpointSlice

In the lab, the readiness probe calls `GET /` on the container's named port `http`:

~~~yaml
readinessProbe:
  httpGet:
    path: /
    port: http
  initialDelaySeconds: 2
  periodSeconds: 5
~~~

Kubernetes updates EndpointSlices/Services once Pods satisfy readiness. With a wrong selector or unready Pods, Ingress/Gateway has zero backends even when URL routing is valid.

~~~bash
kubectl -n shop get pods -o wide
kubectl -n shop describe pod <POD_NAME>

kubectl -n shop get endpointslices \
  -l kubernetes.io/service-name=catalog-svc \
  -o yaml
~~~

For real apps, expose a dedicated readiness endpoint like `/ready` that responds quickly once the process and **critical** dependencies are ready. Never require interactive user login on a health endpoint or probe non-essential dependencies in a way that drops all Pods unready over a minor glitch.

### 13.3. Port mismatches are a frequent cause of failure

In our example:

~~~text
Ingress/HTTPRoute backendRef → Service port 80
Service targetPort "http"    → containerPort 5678
Process listening            → 0.0.0.0:5678
~~~

If the container listens on 5678 while the Service forwards to 8080, traffic fails even when DNS and TLS are spotless.

~~~bash
kubectl -n shop describe service catalog-svc
kubectl -n shop get deployment catalog -o yaml
kubectl -n shop get endpointslices \
  -l kubernetes.io/service-name=catalog-svc
~~~

### 13.4. Rollouts must keep enough healthy backends

During a Deployment rolling update, new Pods must pass readiness before taking traffic. You often need:

- A `startupProbe` matching initialization duration.
- A `readinessProbe` reflecting genuine ability to serve.
- Graceful `SIGTERM` handling and sufficient `terminationGracePeriodSeconds`.
- `PodDisruptionBudget`, topology spread, and replicas for availability.
- Compatible connection draining on the ingress/gateway.

Verify:

~~~bash
kubectl -n shop rollout status deployment/catalog
kubectl -n shop get pods -l app=catalog -o wide
~~~

Never remove probes just to make Pods show Ready; fix actual startup or dependency failures.

## 14. Observing behavior from client to Pod

### 14.1. Key telemetry sources

| Layer | Data source | Questions to answer |
| --- | --- | --- |
| Client/DNS | `nslookup`, `curl`, TLS details | Does the request hit the right frontend? |
| Azure LB/L7 Gateway | Backend health, access logs, metrics | Is the data plane forwarding requests? |
| Ingress/Gateway controller | Reconciliation events, route status, logs | Was config accepted and programmed? |
| Ingress/Gateway access logs | Host, path, upstream status, latency | Where did the HTTP status code originate? |
| Kubernetes Service | EndpointSlices, selectors, ports | Are ready backends present? |
| Pod/Deployment | Restarts, readiness, OOMKilled, image pulls | Is the app running healthily? |
| App/Dependencies | Request traces, DB latency, exceptions | Is app code or a downstream failing? |
| Azure Monitor | Alerts and aggregate metrics | Is the SLO impacted? |

**Note:** an Azure gateway's Kubernetes controller may run only **reconciliation** logic, while HTTP traffic and access logs reside on the Azure gateway resource rather than in controller pod logs.

### 14.2. Read-only inspection commands

~~~bash
kubectl -n shop get deployments,pods,services

kubectl -n shop get ingress -o wide
kubectl -n shop get gateways,httproutes

kubectl -n shop get events \
  --sort-by=.lastTimestamp

kubectl -n shop logs deployment/catalog \
  --tail=100

kubectl -n shop logs deployment/orders \
  --tail=100
~~~

`kubectl get all` does not list all Kubernetes API resource types, so explicitly query `Ingress`, `Gateway`, `HTTPRoute`, `NetworkPolicy`, and related objects.

### 14.3. Find the real controller instead of guessing its namespace

~~~bash
kubectl get ingressclass
kubectl get gatewayclass
kubectl get pods -A
kubectl get services -A
~~~

Use `IngressClass.spec.controller` or `GatewayClass.spec.controllerName` to identify the active implementation. The controller namespace is not necessarily `ingress-nginx`; do not blindly run `kubectl logs -n ingress-nginx` before checking what the cluster actually runs.

If using Azure Application Gateway or Front Door, inspect diagnostic settings, backend health, and WAF logs on the **corresponding Azure resource**. If using an in-cluster proxy controller, read logs/metrics from its data plane pods.

### 14.4. Distributed tracing

A single request can traverse:

~~~text
Client → Gateway → catalog-svc → catalog Pod → Azure SQL
~~~

Use OpenTelemetry / Application Insights or equivalent tooling to correlate a trace ID across hops:

- UTC timestamp, hostname, and path.
- Frontend and upstream HTTP status codes.
- Gateway/route, Service, Pod name, and namespace.
- Pod version and dependency call durations.
- Retry or timeout reasons.

Never log tokens, private keys, or unnecessary user PII. A single "502" line at the gateway is insufficient to distinguish TLS, networking, and application errors.

### 14.5. Alerting suggestions

- Increases in 5xx/502/503 responses and p95/p99 latency on the gateway.
- EndpointSlices for critical Services dropping to zero ready addresses.
- Rising Pod restarts, `OOMKilled`, or `CrashLoopBackOff` events.
- Controller/Gateway failing to reconcile or routes reporting `Accepted=False`.
- TLS certificates nearing expiration.
- External IP/DNS pointing to the wrong target after a change.
- Gateway/Ingress data plane CPU or capacity nearing saturation.
- Unusual WAF blocks or traffic spikes departing from baseline.

Every alert needs a **scope, owner, SLO, and runbook**. Elevated 404s can be normal API behavior; do not assume every 404 is an outage.


## 15. Playbook for diagnosing DNS, TLS, 404, 502, and 503 errors

A user reports: `https://shop.example.com/catalog` is down. Before making edits, record **timestamp, hostname, path, HTTP status, client location**, and recent changes.

### 15.1. Quick triage table

| Symptom | First hypothesis | Next check |
| --- | --- | --- |
| `NXDOMAIN` | Missing DNS record or wrong DNS scope | `nslookup`, public/private DNS zones |
| TCP timeout | Frontend/network/firewall/routing | IP, listener, NSGs, Azure LB/gateway |
| `ERR_CERT_COMMON_NAME_INVALID` | TLS certificate SAN does not match hostname | SNI, cert chain, Secret or Azure cert binding |
| TLS handshake failure | TLS policy, listener, cert/chain | `curl -v`, controller/gateway logs |
| HTTP 404 on a single path | Ingress/HTTPRoute match mismatch or backend returns 404 | Host/path rules, app routes, access logs |
| HTTP 502 | Gateway cannot reach backend or invalid upstream response | Gateway backend health, port, TLS/backend logs |
| HTTP 503 | No healthy backends available or upstream overloaded | Service ready endpoints, Pod readiness, data plane health |
| HTTP 504 | Upstream failed to respond before timeout | Request latency, dependencies, gateway timeout |
| HTTP 403 | Authz/WAF/ingress policy/backend | WAF/access/app logs, policies |
| Works from one namespace, fails from another | NetworkPolicy, DNS, or permissions | Source/destination namespaces, policies, routing |

**HTTP status codes can be generated by either the gateway or the application.** Never conclude from a status code alone without checking logs and route context.

### 15.2. Step 1 — DNS and frontend

~~~bash
nslookup shop.example.com

# Only when the domain and cert are configured by your organization:
curl -v https://shop.example.com/catalog
~~~

If DNS returns the wrong IP, fix DNS records/TTL and verify the real ingress target rather than touching containers. If DNS is right yet TCP times out, check frontend listeners, routing, firewalls, and backend health.

To test a newly provisioned IP before DNS changes:

~~~bash
# 203.0.113.10 is a documentation IP; substitute the real frontend IP.
curl -v \
  --resolve shop.example.com:443:203.0.113.10 \
  https://shop.example.com/catalog
~~~

This test preserves TLS SNI and HTTP `Host` for the real hostname. Never use `curl -k` as a production validation shortcut.

### 15.3. Step 2 — Controller and route status

For Ingress:

~~~bash
kubectl -n shop describe ingress shop-ingress
kubectl get ingressclass
~~~

For Gateway API:

~~~bash
kubectl -n shop describe gateway shop-gateway
kubectl -n shop describe httproute shop-routes
kubectl -n shop get gateway shop-gateway -o yaml
kubectl -n shop get httproute shop-routes -o yaml
~~~

Check:

- Is the class managed and accepted by the controller?
- Do listener host/port match `shop.example.com:443`?
- Does the route attach to the right listener via `parentRefs` and `sectionName`?
- Are `Accepted=True` and `ResolvedRefs=True` reported in parent status?
- Does the controller report reconciliation errors or missing network/identity permissions?
- What is the gateway's actual provisioned address/endpoint?

If Gateway/HTTPRoute APIs are not installed, Gateway commands report resource-not-found—a CRD issue, not a DNS failure.

### 15.4. Step 3 — Check Service and EndpointSlices

~~~bash
kubectl -n shop describe service catalog-svc

kubectl -n shop get endpointslices \
  -l kubernetes.io/service-name=catalog-svc \
  -o wide

kubectl -n shop get pods \
  -l app=catalog \
  -o wide

kubectl -n shop describe deployment catalog
~~~

If the Service lacks ready endpoints, fix Pods, label selectors, readiness, or startup first. If endpoints exist yet 502/503 persists, check ports, network policies, backend HTTP/TLS, and the gateway data plane.

### 15.5. Step 4 — Test the application internally

Use `port-forward` when permitted:

~~~bash
kubectl -n shop port-forward svc/catalog-svc 8081:80
~~~

In another terminal:

~~~bash
curl -i http://127.0.0.1:8081/
~~~

If the app responds cleanly via `port-forward` while public ingress fails, investigate the gateway/controller layer, Azure networking, or backend path. **`port-forward` does not follow the same network path as the gateway**, so success there does not prove gateway connectivity works.

### 15.6. Step 5 — Collect logs and recent change timestamps

~~~bash
kubectl -n shop logs deployment/catalog \
  --tail=100

kubectl -n shop get events \
  --sort-by=.lastTimestamp
~~~

Cross-check ingress/gateway access logs, Azure Monitor, network policies, and deployment history. Avoid deleting or restarting Pods before gathering evidence unless following an approved runbook.

### 15.7. Step 6 — Fix based on evidence

- Wrong DNS → update record after confirming real frontend IP.
- TLS mismatch → issue/attach certificate with matching hostname SAN.
- Wrong IngressClass/GatewayClass → choose a supported controller.
- Rejected HTTPRoute → fix hostname, `parentRefs`, `allowedRoutes`, or `ReferenceGrant`.
- Service selector mismatch → update labels or selectors cleanly.
- Broken readiness → point to a genuine readiness endpoint; never delete probes to hide errors.
- Gateway health probe failing → verify host, path, port, TLS, and networking.
- HTTP 504 → investigate backend/dependency latency before raising timeouts.
- WAF false positive → inspect policy logs and narrow rules carefully.

### 15.8. Step 7 — Verify recovery

Close the incident only when:

1. DNS and certificates are valid.
2. Ingress/Gateway routes are accepted by the controller and show endpoints.
3. Services have ready backends.
4. `/catalog` and `/orders` return expected status codes and payloads.
5. 5xx rates and latency return within SLO.
6. No unintended public entry points or relaxed firewall rules remain.
7. Alerts and logging remain active.

## 16. Scaling, rolling updates, and gateway capacity

### 16.1. Three distinct autoscaling layers

- **Application Pods:** HPA/KEDA adjusts replica counts by metric/event.
- **AKS nodes:** Cluster Autoscaler or other node provisioning mechanisms expand Pod compute capacity per config.
- **Ingress/Gateway data plane:** proxy pods or L7 gateways have their own scaling mechanisms and capacity limits, sometimes Azure-managed.

For example, HPA wants to scale `catalog` from 2 to 8 Pods yet node pools lack capacity; extra Pods stay `Pending`. Conversely, Pods scale up cleanly yet an ingress proxy hits CPU limits or a gateway backend pool saturates, hurting SLOs.

### 16.2. CPU HPA example

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: catalog-hpa
  namespace: shop
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: catalog
  minReplicas: 2
  maxReplicas: 6
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
~~~

Illustrative example only. CPU HPA requires a working metrics pipeline and declared CPU requests; thresholds must be tuned from workload measurements. HPA **does not** create DNS, TLS certs, or public IPs.

### 16.3. Preserving requests during rolling updates

When scaling in or replacing Pods:

- New Pods must pass readiness before receiving traffic.
- Old Pods must receive `SIGTERM` and finish in-flight requests.
- EndpointSlices update as Pod states transition.
- Controllers/gateways may need a brief moment to propagate backend updates.
- For long-running requests, tune `terminationGracePeriodSeconds`, `preStop` hooks, timeouts, and data-plane connection draining.

If requests drop during rollouts, check coordination among readiness, liveness, graceful shutdown, and gateway draining rather than blindly setting all timeouts to infinity.

### 16.4. Canary traffic

Gateway API controllers supporting **weighted `backendRefs`** can direct a percentage of traffic to a canary Service. With Ingress API, canary splitting typically depends on implementation-specific annotations/features.

Safe workflow:

1. Deploy separate stable and canary Services.
2. Verify canary Pod readiness and API compatibility.
3. Shift a small percentage of traffic where supported by the controller.
4. Monitor 5xx rates, latency, and business errors per version.
5. Increase weight gradually while SLOs hold.
6. Roll back routing if errors appear, while assessing any data side effects.

**Rolling back traffic does not automatically roll back database schemas, queues, or data written by the canary.** Backward-compatible API and schema design are essential.

## 17. Securing Ingress and Gateway on AKS

### 17.1. Attack-surface reduction principles

- Expose only required frontends publicly; avoid public `Service` LoadBalancers on private backends.
- Enable HTTPS, manage certificate chains, SANs, rotation, and redirects.
- Enforce WAF, rate limiting, and authentication where needed; TLS does not replace authorization.
- Enforce Kubernetes RBAC, NetworkPolicy, admission policies, and namespace isolation.
- Prevent app teams from altering `GatewayClass`, controllers, or public networking outside authorized scope.
- Keep ingress/gateway controllers and CRDs on **vendor-supported versions** through regular upgrade cycles.
- Manage secrets and certificates with least privilege; never commit private keys.
- Capture useful logs while scrubbing credentials and PII from access logs.

### 17.2. NetworkPolicy and access scope

A backend like `catalog-svc` may only need calls from the gateway data plane and select internal workloads. **NetworkPolicy** restricts Pod-to-Pod traffic via the cluster's CNI/NetworkPolicy engine.

However:

- Traffic from an **Azure-managed external L7 gateway** may not originate from in-cluster Pod labels like an in-cluster ingress controller.
- Network policies govern Pod traffic within supported bounds; Azure NSGs, firewalls, and UDRs remain important.
- Applying a `NetworkPolicy` only enforces rules when AKS has a working NetworkPolicy implementation enabled.
- Never copy a deny-all NetworkPolicy to production without testing probes, DNS, and ingress connectivity first; doing so can cause an outage.

### 17.3. Ingress/Gateway governance roles

| Role | Can manage | Should NOT hold by default |
| --- | --- | --- |
| Cluster/platform owner | `GatewayClass`, controllers, IPs, networking, TLS policies | Read access to all teams' business secrets |
| Namespace application owner | Deployments, Services, HTTPRoutes inside namespace | Cluster-wide RBAC and `GatewayClass` |
| Security owner | WAF, certificate lifecycles, policies, audits | Unnecessary edits to app source code |
| DNS owner | Public/private DNS records | Kubernetes admin on every cluster |
| SRE | Logs, metrics, alerts, rollbacks per scope | Subscription-wide Owner |
| CI/CD identity | Apply manifests in assigned namespaces | Unrelated Azure resource administration |

**Gateway API supports role separation**, yet real enforcement still relies on Kubernetes RBAC and admission/organizational controls. `allowedRoutes` does not replace the authorization layer.

### 17.4. Backend TLS and mTLS

If policy requires encryption all the way to Pods, simply putting a certificate on the frontend does **not give you end-to-end TLS**. Choose among:

- HTTPS to backends per gateway/controller support.
- A service mesh or internal mTLS solution.
- Controlling certificates, SAN/SNI, and trust chains.
- Health probes configured with matching protocol, host, and port.
- Certificate expiration monitoring across every hop.

Never disable TLS verification just to clear a 502 error; fix the root CA, hostname, and certificate chain properly.

## 18. Cost and lifecycle operations

### 18.1. Cost drivers

| Component | Pricing factors |
| --- | --- |
| AKS node pools | VM instances, CPU/RAM, and disks |
| In-cluster ingress controller | Proxy/controller Pods consuming node compute |
| Azure Load Balancer and Public IPs | Frontends, data processing, and IPs per pricing table |
| Application Gateway / App Gateway for Containers | L7 gateway capacity, networking, and SKU-based charges |
| Front Door / WAF | Requests, bandwidth, rules, and plan features |
| Log Analytics / Azure Monitor | Ingestion, retention, metrics, and alerts |
| TLS/PKI and DNS | Managed certificates/DNS services per configuration |
| Egress / data transfer | Cross-zone, cross-network, or Internet traffic |
| Autoscaling | HPA / cluster autoscaler / gateway scaling can raise spend |

Never conclude "one shared Ingress is always cheaper" if workloads require an expensive managed gateway tier; compare **total cost against actual requirements and SLOs**.

### 18.2. Cost of proliferating public endpoints

Each public `LoadBalancer` brings its own frontend resource, public IP, DNS, TLS, and policies. Consolidating APIs behind a gateway lowers management cost while introducing a **shared failure domain**, requiring sufficient gateway capacity, security isolation, and multi-tenant governance.

### 18.3. Lifecycle and change control

Before upgrading cluster versions or controllers:

1. Check API version and CRD compatibility.
2. Check controller support lifecycles and Gateway API feature support.
3. Snapshot/export infrastructure configs via IaC per organizational process.
4. Test in staging, verifying TLS, routes, and backend health.
5. Roll out sequentially during maintenance windows.
6. Keep a rollback plan and avoid resources deprecated/removed in the target version.

Regarding **Ingress** and **Gateway API**, both resource kinds can coexist in the same namespace. Never assume both cleanly manage the same hostname with predictable precedence; avoid **conflicting routes/controllers**.

## 19. Capstone exercise: choosing Ingress or Gateway API?

### 19.1. Business requirements

A team wants to publish:

~~~text
https://shop.example.com/catalog → catalog-svc:80
https://shop.example.com/orders  → orders-svc:80
~~~

Requirements:

- Both backends use `ClusterIP` only, with no dedicated public IPs.
- Valid HTTPS certificates.
- Long-term, the platform team owns the entry point while app teams own their individual routes.
- Plan to canary a portion of `catalog` traffic.
- Monitor 5xx errors, readiness, and cost.

### 19.2. Option A: Ingress

Use Ingress when a controller is already operated and supports required routing/TLS. App teams declare host/path rules; canary splitting or redirects rely on controller-specific annotations or policies.

**Pros:** familiar HTTP host/path model, simple setup for a few teams.  
**Trade-offs:** core Ingress API lacks standard objects for multi-team role boundaries and advanced routing like Gateway API; advanced features depend on the controller.

### 19.3. Option B: Gateway API

The platform team creates `GatewayClass`/`Gateway`, configuring the HTTPS listener and `allowedRoutes`. App teams create `HTTPRoute`s with `parentRefs`, `hostnames`, path matches, and `backendRefs`.

**Pros:** clean separation of duties, extensible route objects, and native weighted `backendRefs` where supported.  
**Trade-offs:** must ensure supported Gateway API CRDs/controllers, handle cross-namespace permissions, and manage `GatewayClass`/data-plane lifecycles.

### 19.4. Acceptance checklist

| Check | Expected outcome | Tool |
| --- | --- | --- |
| Healthy Pods | Both Deployments have Ready replicas | `kubectl get pods`, rollout status |
| Service endpoints | Both Services show ready endpoints | `kubectl get endpointslices` |
| Controller/class | Valid `IngressClass` or `GatewayClass` | `kubectl get/describe` |
| Route status | Ingress has `ADDRESS` or HTTPRoute shows matching `Accepted`/`ResolvedRefs` | `kubectl describe`, status |
| DNS | `shop.example.com` points to right frontend | `nslookup` |
| TLS | Certificate valid for hostname | `curl -v`, cert inspection |
| Host/path | `/catalog` and `/orders` reach matching backends | `curl` |
| Internal backends | Zero unintended public LoadBalancers for backends | `kubectl get svc -A` |
| Observability | HTTP/access logs and metrics flowing | Azure Monitor / controller logs |
| Failure test | When one Pod becomes unready, healthy backends keep serving | Readiness/Endpoints, controlled test |
| Canary | Test split produces zero backend errors | HTTPRoute weight / controller feature |
| Cost | IP/gateway/node/log charges budgeted | Azure Pricing Calculator / Cost Management |

### 19.5. Scenario A: Route exists yet does not work

`kubectl get httproute` shows `shop-routes`, yet `status.parents[].conditions` shows `Accepted=False`.

**Question:** should you update DNS right away?

**Answer:** not yet. Check the Gateway listener, hostname matching, `parentRefs`, `allowedRoutes`, `GatewayClass`/controller, and events. A resource existing in the API does not mean the route was accepted.

### 19.6. Scenario B: TLS passes yet returns 503

Client completes the TLS handshake, yet `GET /catalog` returns 503. `catalog-svc` has 0 ready endpoints.

**Answer:** check Deployment/Pod readiness, labels, `targetPort`, image, and logs; do not touch TLS certificates when evidence points straight to the backend.

### 19.7. Scenario C: Two namespaces required

An `HTTPRoute` in `team-catalog` wants to attach to a Gateway in `network-system` and point to a Service in `team-catalog`.

**Answer:** the Gateway listener must permit routes from the team's namespace (via `allowedRoutes`), while a `backendRef` in the same namespace as the HTTPRoute needs no cross-namespace `ReferenceGrant`. If `backendRef` points to a Service in a third namespace, a `ReferenceGrant` from that target namespace owner may be required.

### 19.8. Scenario D: Gateway behind Front Door

Azure Front Door with WAF sits in front of an AKS gateway, yet the backend's public IP remains open to direct traffic.

**Answer:** restrict unauthorized direct access to the origin via firewalls/authentication and Front Door origin locking; otherwise attackers can bypass WAF.

### 19.9. Controlled lab cleanup

If namespace `shop` was **created solely for this lab** and holds no shared resources, inspect first:

~~~bash
kubectl -n shop get deployments,services,ingresses
kubectl -n shop get gateways,httproutes
kubectl -n shop get secrets
~~~

Only after confirming every resource belongs to the lab and deletion is authorized:

~~~bash
# DESTRUCTIVE operation in lab namespace; never run in Prod.
kubectl delete namespace shop
~~~

Never delete shared organizational Ingress/Gateway controllers, `GatewayClass`, Application Gateway, Azure Front Door, or shared public IPs. Some Azure gateway resources may persist and continue billing even after deleting a Kubernetes namespace, depending on the integration/controller.

## 20. Self-check questions

**Question 1.** Can `Service.type=ClusterIP` be accessed directly from the Internet?

**Answer:** Not in the standard internal service model. Publishing externally requires a configured entry path such as LoadBalancer, Ingress/Gateway, or an external gateway.

**Question 2.** Does creating an Ingress object guarantee AKS automatically provisions a public IP and HTTPS?

**Answer:** No. You need an Ingress controller, `IngressClass`, frontend networking, DNS, certificates, and matching routing. Ingress is a declarative API.

**Question 3.** What is the main difference between Ingress and Gateway API?

**Answer:** Ingress offers relatively simple HTTP/HTTPS host/path rules; Gateway API provides a `GatewayClass`/`Gateway`/route model separating ownership and richer route/filter capabilities per implementation.

**Question 4.** Is `GatewayClass` responsible for running application containers?

**Answer:** No. It selects the gateway controller/implementation; Deployments/Pods and Services provide the application serving path.

**Question 5.** What does an `HTTPRoute` in another namespace need to attach to a Gateway?

**Answer:** The Gateway listener must allow routes from that namespace via `allowedRoutes`; names, hostnames, and `parentRefs` must also match.

**Question 6.** What problem does `ReferenceGrant` solve?

**Answer:** It permits specific cross-namespace references, such as an HTTPRoute targeting a Service in another namespace, granted by the target namespace owner. It does not replace `allowedRoutes` for route attachment.

**Question 7.** When Gateway API reports `ResolvedRefs=False`, what do you check?

**Answer:** Service name, port, namespace, Secret names, and corresponding `ReferenceGrant`/permission constraints.

**Question 8.** A Pod is Ready while the gateway reports unhealthy; is that contradictory?

**Answer:** No. Kubernetes readiness and gateway health checks are independent probes that can target different hosts, paths, protocols, or network paths.

**Question 9.** Why does a Service with a selector not matching Pods break traffic even when Ingress is valid?

**Answer:** The Service has zero ready endpoints to forward traffic to; the controller/gateway has no real backend.

**Question 10.** When HPA scales up Pods, does the ingress data plane automatically scale its capacity?

**Answer:** Not by default. App Pods, AKS nodes, and ingress/gateway data planes have independent scaling mechanisms and limits.

**Question 11.** Which namespace does an Ingress TLS Secret normally belong to?

**Answer:** The same namespace as the Ingress under standard Kubernetes Ingress TLS rules. In Gateway API, `certificateRefs` and namespace rules follow the Gateway implementation and reference permissions.

**Question 12.** Why is `curl --resolve` more useful than calling `https://<IP>` when troubleshooting hostname-based HTTPS?

**Answer:** `--resolve` routes TCP to the target IP while keeping the real hostname in the URL so TLS SNI and the HTTP `Host` header are sent accurately.

**Question 13.** Are Azure Application Gateway with AGIC and Application Gateway for Containers the same product?

**Answer:** No. They have separate data planes, controllers/integrations, and feature scopes; choose the technology matching your version and actual needs.

**Question 14.** If the goal is publishing APIs across multiple regions, what else is needed beyond Ingress/Gateway inside one AKS cluster?

**Answer:** Global routing such as Azure Front Door, WAF, DNS, health failover, backend isolation, data replication, SLOs, and multi-region operational policies.

## Key takeaways

- **Pods** run applications; **`ClusterIP` Services** provide stable backends; **Ingress / Gateway API** declare HTTP/HTTPS access by host/path.
- **Ingress/Gateway resources do not create a data plane on their own**: you need a controller implementation, networking, and frontend addressing.
- **`IngressClass`** picks the Ingress controller; **`GatewayClass`/`Gateway`/`HTTPRoute`** separate gateway governance from route ownership.
- **Gateway API** surfaces `Accepted`, `ResolvedRefs`, and status conditions to verify controller acceptance.
- **DNS, TLS, ingress controllers, Kubernetes Services, EndpointSlices, and Pods** are independent layers to inspect during outages.
- **Public/private ingress differs from a private AKS API server**; exposing backends must pair with network security, authentication, and WAF.
- Deciding among AKS application routing, AGIC, Application Gateway for Containers, and Gateway API depends on **supportability, operational model, security, and cost**.
- During troubleshooting, trace from **client/DNS → frontend/TLS → Ingress/Gateway status → Service endpoints → Pod → dependencies**, and verify SLO recovery after fixing.
