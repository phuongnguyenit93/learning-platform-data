# Order Processing Workflow Project with Retries and Compensation

## 1. Objectives and Context

An e-commerce application must perform multiple steps when a customer places an order: accepting the request, reserving inventory, confirming payment, booking shipment, and finalizing the order. If payment succeeds but booking shipment fails, returning an HTTP error to the buyer **does not automatically refund the payment or release the reserved stock**. If the connection drops right after deducting inventory, retrying without idempotency can deduct inventory twice. These problems become even more likely when steps live across different services or projects.

This hands-on project builds an **orchestrated Saga** on Google Cloud:

- **Google Cloud Workflows** orchestrates the steps, enforces timeouts, performs bounded retries, and invokes compensating actions.
- **Cloud Run** hosts an API simulating Order, Inventory, Payment, and Shipping components. To keep the lab compact, endpoints live in **one** Cloud Run service while preserving clear business boundaries.
- **Firestore in Native mode** stores order state and inventory counts. Transactions protect certain state transitions against concurrent requests.
- **IAM and OIDC** protect Cloud Run; Workflows calls the service using a service account identity.
- **Cloud Logging/Monitoring** provides signals to inspect progress, retry errors, and compensation.

This is a hands-on exercise in the `CLOUD_PROVIDERS_GCP` module, connecting projects, IAM, Cloud Run, and databases with release automation, reliability, and cost. The Payment code only **simulates** charging and refunding via Firestore state; it **does not** connect to a payment gateway, charge real money, or represent a design approved for production financial transactions.

By the end of the project, you should be able to:

1. Start a workflow with a valid order and receive `CONFIRMED` status.
2. Prove a transient HTTP 503 error is retried without recording payment twice.
3. Prove a shipment booking HTTP 422 error triggers compensation in reverse order.
4. Inspect order state after compensation and verify inventory is restored.
5. Distinguish retries, compensation, local transactions, and distributed transactions.
6. Identify controls required before turning this demo into a production system.

## 2. Deliverables and Acceptance Criteria

| Deliverable | Evidence to Collect |
|---|---|
| Private Cloud Run API | Service URL, deployment status, `allUsers` not granted invoke |
| Firestore database | `orders` and `stock` collections reflect state after workflow runs |
| `orders-saga` workflow | Deployed successfully with execution history |
| Happy path | Order `CONFIRMED`, inventory `RESERVED`, payment `CHARGED`, shipment `BOOKED` |
| Transient-failure test | First payment request returns 503, retry succeeds; only one `CHARGED` effect |
| Business-failure test | Shipping returns 422, payment `REFUNDED`, inventory `RELEASED`, order `CANCELLED` |
| Duplicate test | Re-sending the same `order_id`/payload does not deduct stock or charge again |
| Logs and report | Execution ID, order ID, per-step errors, compensation outcome |

`CHARGED`/`REFUNDED` states in the demo are data labels only, not reconciliation results with a real payment provider.

## 3. Architecture and Execution Flow

~~~mermaid
flowchart LR
    U[Client / tester] --> W[Google Cloud Workflows]
    W -->|OIDC| A[Cloud Run orders-saga-api]
    A --> O[Order endpoints]
    A --> I[Inventory endpoints]
    A --> P[Payment mock endpoints]
    A --> S[Shipping mock endpoints]
    O --> F[(Firestore)]
    I --> F
    P --> F
    S --> F
    W -. audit / metrics .-> M[Cloud Logging / Monitoring]
~~~

Success flow:

~~~mermaid
sequenceDiagram
    participant W as Workflows
    participant A as Cloud Run API
    participant D as Firestore
    W->>A: POST /orders (idempotency = order_id)
    A->>D: Create PENDING order if absent
    W->>A: POST /orders/{id}/reserve
    A->>D: Deduct inventory once
    W->>A: POST /orders/{id}/charge
    A->>D: Mark CHARGED once
    W->>A: POST /orders/{id}/ship
    A->>D: Mark BOOKED once
    W->>A: POST /orders/{id}/confirm
    A->>D: Transition order to CONFIRMED
    A-->>W: Done
~~~

When a later step fails, compensating actions are invoked in **reverse order**:

~~~mermaid
flowchart TD
    X[Failure after Saga started] --> A[Cancel shipment, if booked]
    A --> B[Refund payment, if charged]
    B --> C[Release inventory, if reserved]
    C --> D[Cancel order if state allows]
    D --> E{All compensations succeeded?}
    E -->|Yes| F[COMPENSATED]
    E -->|No| G[COMPENSATION_PENDING and reconcile]
~~~

Key point: Workflows **cannot roll back a transaction already committed in another service**. Each step must expose a semantically meaningful compensating action. A refund is a new transaction; releasing inventory conditionally increments stock back; cancelling a shipment may fail if the parcel has already shipped.

## 4. Business Definitions, Errors, and States

### Steps and Compensating Actions

| Forward action | Success | Compensation | Desired Guarantee |
|---|---|---|---|
| Create order | `PENDING` | Cancel order | Same `order_id` + payload creates only once |
| Reserve inventory | `RESERVED` | Release inventory | Never deduct/restore the same reservation twice |
| Charge payment (simulated) | `CHARGED` | Refund payment | Idempotency key bound to order and action type |
| Book shipment | `BOOKED` | Cancel shipment | Cancel while still in a cancellable state |
| Confirm order | `CONFIRMED` | No auto-undo after confirmation | Business commit boundary of this demo |

### Error Classification

- **Transient:** 429/502/503/504, dropped connections, or timeouts; retry when the operation is designed to be idempotent.
- **Business/permanent:** out of stock 409, invalid address 422, access denied 403; do not retry indefinitely.
- **Unknown outcome:** response lost after the server committed. Never assume the request did not run; require idempotency and state lookup.
- **Compensation failure:** compensation fails after bounded retries; keep `COMPENSATION_PENDING` status and require a recovery workflow.

In this demo, once an order is `CONFIRMED` it **cannot** be cancelled/refunded/released by compensation endpoints. If confirmation succeeds on the server but Workflows loses the response, compensation is blocked; the system must **reconcile state** instead of refunding a confirmed order. In real systems, "shipped" or "settled" states establish even stronger business boundaries.

### Idempotency and Retries

Assign a stable `order_id` from the originating request rather than generating a new ID per retry. On the server, compare the payload of duplicate requests and return 409 if the same ID arrives with different contents. Each step updates state inside a Firestore transaction; if the state already reflects the desired outcome, return 200 without re-applying the side effect.

Workflows only retries a POST operation when **that endpoint's own contract** guarantees idempotency. Never attach default idempotent retries to every POST in production systems.

## 5. Preparing Google Cloud and Permissions

### Entry Requirements

- A dedicated Google Cloud test project with billing enabled and deployment permissions.
- Signed-in Google Cloud CLI, suitable Python 3, and a Bash terminal (Cloud Shell works).
- Permissions to enable APIs, manage service accounts/IAM, and create Cloud Run, Workflows, and Firestore resources.
- A budget/alert on the project to catch unintended running resources.

Example project and region selection (replace with your values):

~~~bash
export PROJECT_ID="your-saga-lab-project"
export REGION="asia-southeast1"
export RUN_SA="saga-api-sa@$PROJECT_ID.iam.gserviceaccount.com"
export WORKFLOW_SA="saga-workflow-sa@$PROJECT_ID.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID"

gcloud services enable \
  run.googleapis.com \
  workflows.googleapis.com \
  firestore.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com
~~~

Create two separate service accounts:

~~~bash
gcloud iam service-accounts create saga-api-sa \
  --display-name="Order saga Cloud Run runtime"

gcloud iam service-accounts create saga-workflow-sa \
  --display-name="Order saga Workflows identity"
~~~

The Cloud Run runtime needs Firestore read/write access. For a lab using a dedicated project and single database, you can use the role below at project scope; in production, narrow scope with IAM Conditions/custom roles and environment isolation:

~~~bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$RUN_SA" \
  --role="roles/datastore.user"
~~~

### Creating the Firestore Database

If the project **does not yet have** a default database:

~~~bash
gcloud firestore databases create \
  --database="(default)" \
  --location="$REGION" \
  --edition=standard \
  --type=firestore-native
~~~

Check whether a database already exists before running create; never delete a database containing active data. Firestore location cannot be arbitrarily changed after creation. The demo uses the Firestore Server SDK with service account IAM, not the browser Firebase client SDK.

## 6. Structuring the Sample Application

In a demo folder **on the learner's machine** (not this module's documentation folder), create these files:

~~~text
orders-saga-lab/
  main.py
  requirements.txt
  Procfile
  workflow.yaml
~~~

Contents of `requirements.txt`:

~~~text
Flask>=3,<4
google-cloud-firestore>=2,<3
gunicorn>=22,<25
~~~

Contents of `Procfile`:

~~~text
web: gunicorn --bind :$PORT main:app
~~~

Examples use version ranges for illustration; real systems must pin dependency versions and scan for vulnerabilities in CI. Using a single Cloud Run service is for lab convenience, not a mandatory deployment architecture.

## 7. Cloud Run API: Idempotent State Writes with Firestore

### Design Principles

The endpoints expose simple contracts:

- `POST /orders`: creates an order, using `order_id` as the idempotency key.
- `POST /orders/{id}/reserve`: deducts stock if not yet reserved.
- `POST /orders/{id}/charge`: marks payment `CHARGED`.
- `POST /orders/{id}/ship`: marks shipment `BOOKED`.
- `POST /orders/{id}/confirm`: marks `CONFIRMED` if all steps completed.
- `POST /orders/{id}/cancel-shipment`, `/refund`, `/release`, `/cancel`: compensation.
- `GET /orders/{id}`: inspects state after Workflows finishes.

Every request may be invoked multiple times. Demo document stored in Firestore:

~~~json
{
  "order_id": "demo-001",
  "sku": "sku-001",
  "quantity": 2,
  "amount_cents": 2500,
  "status": "PENDING",
  "inventory_state": "NONE",
  "payment_state": "NONE",
  "shipping_state": "NONE",
  "fail_payment_once": false,
  "fail_shipping": false,
  "payment_failure_injected": false
}
~~~

`fail_payment_once` and `fail_shipping` are **strictly for fault injection in the lab**. Never accept client flags that inject failure behavior in production.

### `main.py` Source (Runnable Sample App)

~~~python
import re
from flask import Flask, jsonify, request
from google.cloud import firestore

app = Flask(__name__)
db = firestore.Client()

FORWARD = {"reserve", "charge", "ship", "confirm"}
COMPENSATIONS = {"cancel-shipment", "refund", "release", "cancel"}
ALL_ACTIONS = FORWARD | COMPENSATIONS


def respond(payload, status=200):
    return jsonify(payload), status


def valid_key(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value)


@app.post("/orders")
def create_order():
    body = request.get_json(silent=True) or {}
    order_id = body.get("order_id")
    sku = body.get("sku")
    qty = body.get("quantity")
    amount = body.get("amount_cents")

    if not valid_key(order_id) or not valid_key(sku):
        return respond({"error": "INVALID_ID_OR_SKU"}, 400)
    if type(qty) is not int or not (1 <= qty <= 10):
        return respond({"error": "INVALID_QUANTITY"}, 400)
    if type(amount) is not int or not (0 <= amount <= 10000000):
        return respond({"error": "INVALID_AMOUNT"}, 400)

    identity = {
        "order_id": order_id,
        "sku": sku,
        "quantity": qty,
        "amount_cents": amount,
        "fail_payment_once": body.get("fail_payment_once", False) is True,
        "fail_shipping": body.get("fail_shipping", False) is True,
    }
    ref = db.collection("orders").document(order_id)

    @firestore.transactional
    def create(tx):
        existing = ref.get(transaction=tx)
        if existing.exists:
            old = existing.to_dict()
            if any(old.get(k) != v for k, v in identity.items()):
                return {"error": "IDEMPOTENCY_CONFLICT"}, 409
            return {"order_id": order_id, "status": old["status"],
                    "deduplicated": True}, 200
        tx.set(ref, {
            **identity,
            "status": "PENDING",
            "inventory_state": "NONE",
            "payment_state": "NONE",
            "shipping_state": "NONE",
            "payment_failure_injected": False,
        })
        return {"order_id": order_id, "status": "PENDING"}, 200

    return respond(*create(db.transaction()))


@app.get("/orders/<order_id>")
def get_order(order_id):
    if not valid_key(order_id):
        return respond({"error": "INVALID_ID"}, 400)
    snap = db.collection("orders").document(order_id).get()
    if not snap.exists:
        return respond({"error": "NOT_FOUND"}, 404)
    return respond(snap.to_dict())


@app.post("/orders/<order_id>/<action>")
def order_action(order_id, action):
    if not valid_key(order_id) or action not in ALL_ACTIONS:
        return respond({"error": "UNKNOWN_ACTION"}, 404)

    ref = db.collection("orders").document(order_id)

    @firestore.transactional
    def mutate(tx):
        snap = ref.get(transaction=tx)
        if not snap.exists:
            # Compensation before an order is created must be a no-op.
            if action in COMPENSATIONS:
                return {"result": "NOTHING_TO_COMPENSATE"}, 200
            return {"error": "ORDER_NOT_FOUND"}, 404

        data = snap.to_dict()
        status = data["status"]

        if status == "CANCELLED":
            if action in COMPENSATIONS:
                return {"result": "ALREADY_CANCELLED"}, 200
            return {"error": "ORDER_CANCELLED"}, 409

        if status == "CONFIRMED":
            if action == "confirm":
                return {"result": "ALREADY_CONFIRMED"}, 200
            if action in COMPENSATIONS:
                return {"error": "CONFIRMED_REQUIRES_RECONCILIATION"}, 409
            # A duplicate execution may only confirm steps already completed.
            done = {
                "reserve": data["inventory_state"] == "RESERVED",
                "charge": data["payment_state"] == "CHARGED",
                "ship": data["shipping_state"] == "BOOKED",
            }
            return ({"result": "ALREADY_DONE"}, 200) if done[action] else (
                {"error": "INVALID_CONFIRMED_STATE"}, 409)

        if action == "reserve":
            if data["inventory_state"] == "RESERVED":
                return {"result": "ALREADY_RESERVED"}, 200
            if data["inventory_state"] != "NONE":
                return {"error": "RESERVATION_ALREADY_RELEASED"}, 409
            stock = db.collection("stock").document(data["sku"])
            stock_snapshot = stock.get(transaction=tx)
            available = stock_snapshot.get("available") if stock_snapshot.exists else 10
            if available < data["quantity"]:
                return {"error": "OUT_OF_STOCK"}, 409
            tx.set(stock, {"available": available - data["quantity"]})
            tx.update(ref, {"inventory_state": "RESERVED"})
            return {"result": "RESERVED"}, 200

        if action == "charge":
            if data["payment_state"] == "CHARGED":
                return {"result": "ALREADY_CHARGED"}, 200
            if data["payment_state"] != "NONE" or data["inventory_state"] != "RESERVED":
                return {"error": "PAYMENT_PRECONDITION_FAILED"}, 409
            if data["fail_payment_once"] and not data["payment_failure_injected"]:
                tx.update(ref, {"payment_failure_injected": True})
                return {"error": "INJECTED_TRANSIENT_FAILURE"}, 503
            tx.update(ref, {"payment_state": "CHARGED"})
            return {"result": "CHARGED"}, 200

        if action == "ship":
            if data["shipping_state"] == "BOOKED":
                return {"result": "ALREADY_BOOKED"}, 200
            if data["shipping_state"] != "NONE" or data["payment_state"] != "CHARGED":
                return {"error": "SHIP_PRECONDITION_FAILED"}, 409
            if data["fail_shipping"]:
                return {"error": "SHIPPING_ADDRESS_REJECTED"}, 422
            tx.update(ref, {"shipping_state": "BOOKED"})
            return {"result": "BOOKED"}, 200

        if action == "confirm":
            if (data["inventory_state"], data["payment_state"],
                    data["shipping_state"]) != ("RESERVED", "CHARGED", "BOOKED"):
                return {"error": "ORDER_NOT_READY"}, 409
            tx.update(ref, {"status": "CONFIRMED"})
            return {"result": "CONFIRMED"}, 200

        if action == "cancel-shipment":
            if data["shipping_state"] == "BOOKED":
                tx.update(ref, {"shipping_state": "CANCELLED"})
                return {"result": "SHIPMENT_CANCELLED"}, 200
            return {"result": "NO_SHIPMENT_TO_CANCEL"}, 200

        if action == "refund":
            if data["payment_state"] == "CHARGED":
                tx.update(ref, {"payment_state": "REFUNDED"})
                return {"result": "REFUNDED"}, 200
            return {"result": "NO_PAYMENT_TO_REFUND"}, 200

        if action == "release":
            if data["inventory_state"] == "RESERVED":
                stock = db.collection("stock").document(data["sku"])
                stock_snapshot = stock.get(transaction=tx)
                available = stock_snapshot.get("available") if stock_snapshot.exists else 0
                tx.set(stock, {"available": available + data["quantity"]})
                tx.update(ref, {"inventory_state": "RELEASED"})
                return {"result": "RELEASED"}, 200
            return {"result": "NO_RESERVATION_TO_RELEASE"}, 200

        if action == "cancel":
            if (data["inventory_state"] == "RESERVED"
                    or data["payment_state"] == "CHARGED"
                    or data["shipping_state"] == "BOOKED"):
                return {"error": "COMPENSATION_INCOMPLETE"}, 409
            tx.update(ref, {"status": "CANCELLED"})
            return {"result": "ORDER_CANCELLED"}, 200

        return {"error": "INVALID_ACTION"}, 400

    return respond(*mutate(db.transaction()))
~~~

### Limitations of the Demo Code

- Initial stock is mocked at 10 units the first time a SKU is seen; production must manage inventory through dedicated stock-receiving workflows.
- Stock and order data share Firestore, so transactions guarantee atomicity **within Firestore**. When Inventory, Payment, and Shipping are split into independent services/databases, there is **no shared transaction**; a true Saga with outbox/inbox or durable journal must be used.
- The refund step in the demo only flips a field. With a real payment provider, you need dedicated idempotency keys, charge/refund reconciliation, and handling of unknown responses.
- Two Workflows executions using the same `order_id` can interleave steps; the demo blocks some duplicate effects via transactions, but lacks **execution-level lease/fencing by `execution_id`** to ensure only one coordinator drives an order at a time.
- Cloud Run Invoker IAM protects the whole service, without per-endpoint RBAC. Production must separate admin, operator, and service-to-service permissions.
- Never use the lab to process real money, physical goods, or customer data.

## 8. Deploying the Private Cloud Run API

From the `orders-saga-lab` directory containing `main.py`, `requirements.txt`, and `Procfile`:

~~~bash
gcloud run deploy orders-saga-api \
  --source . \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --service-account="$RUN_SA" \
  --no-allow-unauthenticated

export API_BASE_URL="$(gcloud run services describe orders-saga-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format='value(status.url)')"

echo "$API_BASE_URL"
~~~

Source deployment requires Cloud Build/Artifact Registry permissions and Service Account User on the deployer account per current Cloud Run documentation. Creating the service can incur build and runtime charges.

Allow the Workflows service account to invoke this specific service:

~~~bash
gcloud run services add-iam-policy-binding orders-saga-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --member="serviceAccount:$WORKFLOW_SA" \
  --role="roles/run.invoker"
~~~

Do not grant `allUsers` `roles/run.invoker` for testing convenience. Users running `gcloud` Workflows commands need permissions to deploy and execute Workflows; users directly calling Cloud Run to GET order state need Invoker permission separately.

## 9. Defining the Workflow with Retries and Compensation

Workflows calls Cloud Run over HTTP POST with OIDC authentication. `API_BASE_URL` is configured at deploy time rather than passed from user input. Every POST endpoint in this demo has an idempotent contract, so we use the default retry predicate for idempotent operations with 3 retries after the initial attempt. This policy retries connection/timeout errors and HTTP 429, 502, 503, and 504; business errors like 409/422 are not retried.

Contents of `workflow.yaml`:

~~~yaml
main:
  params: [order]
  steps:
    - initialize:
        assign:
          - base_url: ${sys.get_env("API_BASE_URL")}
          - order_id: ${order.order_id}
          - failed_reason: ""
          - compensation_pending: []

    - run_saga:
        try:
          steps:
            - create_order:
                try:
                  call: http.post
                  args:
                    url: ${base_url + "/orders"}
                    auth:
                      type: OIDC
                      audience: ${base_url}
                    headers:
                      Content-Type: application/json
                    body: ${order}
                    timeout: 20
                retry:
                  predicate: ${http.default_retry_predicate}
                  max_retries: 3
                  backoff:
                    initial_delay: 1
                    max_delay: 8
                    multiplier: 2

            - reserve_inventory:
                try:
                  call: http.post
                  args:
                    url: ${base_url + "/orders/" + order_id + "/reserve"}
                    auth:
                      type: OIDC
                      audience: ${base_url}
                    body: {}
                    timeout: 20
                retry:
                  predicate: ${http.default_retry_predicate}
                  max_retries: 3
                  backoff:
                    initial_delay: 1
                    max_delay: 8
                    multiplier: 2

            - charge_payment:
                try:
                  call: http.post
                  args:
                    url: ${base_url + "/orders/" + order_id + "/charge"}
                    auth:
                      type: OIDC
                      audience: ${base_url}
                    body: {}
                    timeout: 20
                retry:
                  predicate: ${http.default_retry_predicate}
                  max_retries: 3
                  backoff:
                    initial_delay: 1
                    max_delay: 8
                    multiplier: 2

            - book_shipment:
                try:
                  call: http.post
                  args:
                    url: ${base_url + "/orders/" + order_id + "/ship"}
                    auth:
                      type: OIDC
                      audience: ${base_url}
                    body: {}
                    timeout: 20
                retry:
                  predicate: ${http.default_retry_predicate}
                  max_retries: 3
                  backoff:
                    initial_delay: 1
                    max_delay: 8
                    multiplier: 2

            - confirm_order:
                try:
                  call: http.post
                  args:
                    url: ${base_url + "/orders/" + order_id + "/confirm"}
                    auth:
                      type: OIDC
                      audience: ${base_url}
                    body: {}
                    timeout: 20
                retry:
                  predicate: ${http.default_retry_predicate}
                  max_retries: 3
                  backoff:
                    initial_delay: 1
                    max_delay: 8
                    multiplier: 2

        except:
          as: saga_error
          steps:
            - capture_failure:
                assign:
                  - failed_reason: ${saga_error.message}

            # Compensation runs in reverse order and does not halt on the first error.
            - cancel_shipment:
                try:
                  call: http.post
                  args:
                    url: ${base_url + "/orders/" + order_id + "/cancel-shipment"}
                    auth:
                      type: OIDC
                      audience: ${base_url}
                    body: {}
                    timeout: 20
                retry:
                  predicate: ${http.default_retry_predicate}
                  max_retries: 3
                  backoff:
                    initial_delay: 1
                    max_delay: 8
                    multiplier: 2
                except:
                  as: cancel_ship_error
                  steps:
                    - note_cancel_ship:
                        assign:
                          - compensation_pending: ${list.concat(compensation_pending, "cancel-shipment")}

            - refund_payment:
                try:
                  call: http.post
                  args:
                    url: ${base_url + "/orders/" + order_id + "/refund"}
                    auth:
                      type: OIDC
                      audience: ${base_url}
                    body: {}
                    timeout: 20
                retry:
                  predicate: ${http.default_retry_predicate}
                  max_retries: 3
                  backoff:
                    initial_delay: 1
                    max_delay: 8
                    multiplier: 2
                except:
                  as: refund_error
                  steps:
                    - note_refund:
                        assign:
                          - compensation_pending: ${list.concat(compensation_pending, "refund")}

            - release_inventory:
                try:
                  call: http.post
                  args:
                    url: ${base_url + "/orders/" + order_id + "/release"}
                    auth:
                      type: OIDC
                      audience: ${base_url}
                    body: {}
                    timeout: 20
                retry:
                  predicate: ${http.default_retry_predicate}
                  max_retries: 3
                  backoff:
                    initial_delay: 1
                    max_delay: 8
                    multiplier: 2
                except:
                  as: release_error
                  steps:
                    - note_release:
                        assign:
                          - compensation_pending: ${list.concat(compensation_pending, "release")}

            - cancel_order:
                try:
                  call: http.post
                  args:
                    url: ${base_url + "/orders/" + order_id + "/cancel"}
                    auth:
                      type: OIDC
                      audience: ${base_url}
                    body: {}
                    timeout: 20
                retry:
                  predicate: ${http.default_retry_predicate}
                  max_retries: 3
                  backoff:
                    initial_delay: 1
                    max_delay: 8
                    multiplier: 2
                except:
                  as: cancel_order_error
                  steps:
                    - note_cancel_order:
                        assign:
                          - compensation_pending: ${list.concat(compensation_pending, "cancel")}

            - decide_compensation:
                switch:
                  - condition: ${len(compensation_pending) == 0}
                    return:
                      order_id: ${order_id}
                      status: "COMPENSATED"
                      failure: ${failed_reason}
                      pending: []

            - manual_recovery_required:
                return:
                  order_id: ${order_id}
                  status: "COMPENSATION_PENDING"
                  failure: ${failed_reason}
                  pending: ${compensation_pending}

    - success:
        return:
          order_id: ${order_id}
          status: "CONFIRMED"
          pending: []
~~~

### Why Does Compensation Call Even Steps That Were Not Executed?

After a timeout, Workflows may not know whether an endpoint applied its side effect or not. Therefore, the demo calls compensating actions in reverse order **regardless of whether the forward step's response was received**. Each compensation checks Firestore state: if never booked/charged/reserved, it returns a no-op; if executed, it undoes it exactly once.

This is a **lab simplification**. In real systems, every participant needs clear contracts on operation status, cancellation eligibility, idempotency scope, and compensation order. You cannot casually call refund before knowing whether a charge actually happened, especially with external payment providers.

### Why Not Return HTTP 500 When Compensation Completes?

In the lab, Workflows returns a result containing `status` as `COMPENSATED` or `COMPENSATION_PENDING` for clear observation. A Workflows execution may end in `SUCCEEDED` state even though **the order failed from a business standpoint**. Production must emit business outcome metrics, events, or a dedicated job-state table and alert whenever `compensation_pending` is non-empty, rather than watching execution status alone.

## 10. Deploying the Workflow and Assigning Permissions

Keep the API URL in workflow configuration rather than trusting a user-supplied URL:

~~~bash
gcloud workflows deploy orders-saga \
  --source=workflow.yaml \
  --location="$REGION" \
  --project="$PROJECT_ID" \
  --service-account="$WORKFLOW_SA" \
  --set-env-vars="API_BASE_URL=$API_BASE_URL"
~~~

Deployers need permission to create/update workflows and `actAs` on the service account; callers running Workflows need execution permission such as `roles/workflows.invoker` or equivalent.

Workflow calls set the OIDC audience to the **Cloud Run base URL**, not the full URL with `/orders/...`; this matters when the service requires authentication. The Cloud Run runtime service account and the Workflows service account are two distinct identities.

## 11. Testing Scenario 1: Happy Path

Run:

~~~bash
gcloud workflows run orders-saga \
  --location="$REGION" \
  --project="$PROJECT_ID" \
  --data='{"order_id":"demo-success-001","sku":"sku-success-001","quantity":2,"amount_cents":2500,"fail_payment_once":false,"fail_shipping":false}'
~~~

Expected `result` output:

~~~json
{
  "order_id": "demo-success-001",
  "status": "CONFIRMED",
  "pending": []
}
~~~

Inspect the order using an account granted Cloud Run Invoker:

~~~bash
curl -fsS \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "$API_BASE_URL/orders/demo-success-001"
~~~

Expected state: `status` `CONFIRMED`, `inventory_state` `RESERVED`, `payment_state` `CHARGED`, `shipping_state` `BOOKED`. For a new SKU, mocked initial stock is 10, so reserving `quantity=2` leaves 8. The account running `curl` needs permission to invoke the private Cloud Run service; receiving 403 does not mean Workflows failed.

## 12. Testing Scenario 2: Retrying a Transient 503 Error

Set `fail_payment_once=true` so the charge endpoint returns HTTP 503 once before recording `CHARGED`:

~~~bash
gcloud workflows run orders-saga \
  --location="$REGION" \
  --project="$PROJECT_ID" \
  --data='{"order_id":"demo-retry-001","sku":"sku-retry-001","quantity":2,"amount_cents":2500,"fail_payment_once":true,"fail_shipping":false}'
~~~

The expected result is still `CONFIRMED`. GET order should show:

~~~json
{
  "order_id": "demo-retry-001",
  "payment_failure_injected": true,
  "payment_state": "CHARGED",
  "status": "CONFIRMED"
}
~~~

This is a **subset** of fields in the document, not the full response. `payment_failure_injected` proves the first call hit the injected error and the retry completed. Inspecting execution history shows `charge_payment` retrying per the retry config.

Re-run with the **exact same payload and `order_id`**:

~~~bash
gcloud workflows run orders-saga \
  --location="$REGION" \
  --project="$PROJECT_ID" \
  --data='{"order_id":"demo-retry-001","sku":"sku-retry-001","quantity":2,"amount_cents":2500,"fail_payment_once":true,"fail_shipping":false}'
~~~

Endpoints see the target state is already reached and return `ALREADY_DONE` or `ALREADY_CONFIRMED`; stock is not deducted again. Reusing the same `order_id` with a changed `quantity` or `amount_cents` must return `IDEMPOTENCY_CONFLICT` (409), never silently overwriting the payload to create a "new version of the order".

## 13. Testing Scenario 3: Shipping Failure and Compensation

Use a fresh SKU and enable `fail_shipping=true`:

~~~bash
gcloud workflows run orders-saga \
  --location="$REGION" \
  --project="$PROJECT_ID" \
  --data='{"order_id":"demo-compensate-001","sku":"sku-compensate-001","quantity":3,"amount_cents":4000,"fail_payment_once":false,"fail_shipping":true}'
~~~

Expected sequence:

1. `PENDING` order is created.
2. Inventory `RESERVED`, stock drops from 10 to 7.
3. Payment `CHARGED`.
4. Shipping returns 422 (business error, not retried).
5. Cancel shipment is a no-op since not `BOOKED`.
6. Refund transitions `CHARGED` → `REFUNDED`.
7. Release inventory transitions `RESERVED` → `RELEASED`; stock returns to 10.
8. Cancel order transitions `PENDING` → `CANCELLED`.
9. Workflow returns `COMPENSATED` with empty `pending`.

Illustrative output:

~~~json
{
  "order_id": "demo-compensate-001",
  "status": "COMPENSATED",
  "pending": [],
  "failure": "HTTP server responded with error code 422"
}
~~~

The exact `failure` string depends on error mapping. Checking Firestore must show **`status` `CANCELLED`, `inventory_state` `RELEASED`, `payment_state` `REFUNDED`, `shipping_state` `NONE`**. Stock for the new SKU must be back at 10. Workflows does not rewrite the past charge; it issues an explicit compensating action.

## 14. Testing Scenario 4: Early-Step Failure

In the demo, each SKU starts with stock 10. Order `quantity=10` for a fresh SKU, then place another order for the same SKU (e.g., 2 units) to trigger out-of-stock:

~~~bash
# First reserve all 10 units of SKU shared-demo.
gcloud workflows run orders-saga \
  --location="$REGION" --project="$PROJECT_ID" \
  --data='{"order_id":"demo-stock-keeper","sku":"shared-demo","quantity":10,"amount_cents":1000}'

# Next order cannot reserve.
gcloud workflows run orders-saga \
  --location="$REGION" --project="$PROJECT_ID" \
  --data='{"order_id":"demo-out-of-stock","sku":"shared-demo","quantity":2,"amount_cents":1000}'
~~~

The second order's reserve call returns 409 `OUT_OF_STOCK`. Workflows should not retry this business error; the second order's compensation performs no-ops and marks `CANCELLED`. It **must not** release inventory held by `demo-stock-keeper`. Stock for `shared-demo` remains 0.

## 15. Designing Handling for Incomplete Compensation

Not every compensation succeeds. For example, a payment provider recorded a charge, but an outage prevents refunds from succeeding for several minutes. You must not:

- Report the order as fully `CANCELLED` while payment remains `CHARGED`.
- Proceed with a new order reusing a reservation whose state is uncertain.
- Retry refunds infinitely or issue multiple refund requests under new IDs.
- Delete the order record thinking the workflow is finished.

### Proposed States

| State | Meaning | Action |
|---|---|---|
| `CONFIRMED` | Forward steps confirmed | Terminal; refunds/exchanges follow separate business flows |
| `COMPENSATED` | Compensating actions succeeded or were no-ops | Controlled failure termination |
| `COMPENSATION_PENDING` | At least one compensating action remains unverified | Needs recovery worker/queue and alert |
| `RECONCILIATION_REQUIRED` | Actual step outcome uncertain, or finalize may have succeeded | Query source of truth before deciding |

In the demo `workflow.yaml`, when a compensation fails after retries, its step name is appended to `compensation_pending` and the workflow keeps running the remaining compensations. The `cancel_order` endpoint refuses while payment is `CHARGED`, shipment is `BOOKED`, or inventory is `RESERVED`. Thus, a failed refund prevents falsely marking the order `CANCELLED`. However, `COMPENSATION_PENDING` **exists only in the execution result** unless the system adds a durable job ledger/recovery worker.

### Production Plan for Compensating Actions

1. Persist Saga ID, execution ID, step state, and idempotency key in a durable journal table.
2. Record deadline, retry count, last error, next retry time, and owner.
3. Use Cloud Tasks or a recovery queue/worker to retry compensation with bounded attempts.
4. Query current state from the participant before each retry.
5. Maintain an error queue and manual intervention runbook when retry budgets exhaust.
6. Mark completed only after verifying all effects requiring rollback are settled.
7. Never auto-compensate a `CONFIRMED` order solely because a finalize response was lost.

The most important rule is that **unknown outcome does not mean failed outcome**. Before triggering hard-to-reverse refunds or cancellations, reconcile against the authoritative data source.

## 16. Preventing Race Conditions and Duplicate Workflow Runs

Firestore transactions in the demo keep operations on the same order from blindly overwriting each other. A real-world Saga also requires:

- **Execution lease:** only one coordinator owns an order at a time, enforced with a TTL and fencing token.
- **Step journal:** states `NOT_STARTED`, `STARTED`, `SUCCEEDED`, `FAILED`, `COMPENSATING`, `COMPENSATED`.
- **Stable idempotency key:** e.g., `order_id + action + version`, passed through to payment providers too.
- **Outbox/inbox:** record state and event in the same local transaction; publish later with deduplication.
- **Monotonic transitions:** once `CONFIRMED`, state cannot revert to `PENDING`.
- **Reconciliation job:** find orders stuck too long and reconcile payment, inventory, and shipment.

Two workflows sharing an `order_id` can interleave steps: one execution may be charging while another hits an error and starts refunding. Idempotent endpoints are necessary, yet **insufficient** to guarantee Saga ordering. In production, pass an owner token and reject commands carrying stale tokens at each participant.

## 17. Observability and Measuring Reliability

### Logging and Correlation

Logs should include: `order_id`, `saga_id`, `execution_id`, `step`, `attempt`, `error code`, a non-sensitive idempotency key, `compensation state`, and `duration`. Avoid logging card numbers, tokens, customer addresses, or payment details.

Cloud Logging and Workflows execution history help trace execution paths. In production apps, emit OpenTelemetry traces and business metrics rather than relying solely on Workflows `SUCCEEDED`/`FAILED`.

### Suggested SLIs/SLOs

| SLI | Definition | Illustrative Target |
|---|---|---|
| Order completion ratio | Confirmed orders / valid started orders | Per product goal |
| Saga duration p95/p99 | Time from start to terminal state | p95 under 10s in this demo |
| Retry rate | Retries / total API step calls | Detect unstable dependencies |
| Compensation success ratio | Fully compensated Sagas / Sagas needing compensation | Near 100%; alert on backlog |
| Compensation backlog age | Age of `COMPENSATION_PENDING` orders | Alert past committed threshold |
| Duplicate suppression | Duplicate requests properly deduplicated | Zero double charges/reserves |
| Business-error breakdown | `OUT_OF_STOCK`, `SHIPPING_ADDRESS_REJECTED`, etc. | Guide business improvements |

Figures are illustrative; do not apply a 10-second p95 to real physical shipping workflows. Workflows bills by step count and execution type; retries also add billable steps, so bound retries/backoff and avoid tight polling loops.

## 18. Least Privilege and Production Safety

- Keep Cloud Run private; only service accounts granted `roles/run.invoker` can call it.
- The Workflow service account does not need `roles/editor` or direct Firestore access.
- The Cloud Run runtime service account receives only required data access; the lab grants `datastore.user` in a dedicated project.
- Execution callers only need necessary Workflows invoke permissions and must not edit target URLs or workflow definitions.
- Never put API keys or payment secrets in workflow source; use Secret Manager with narrow permissions where genuinely needed.
- Every participant validates on the server rather than trusting client parameters blindly.
- Configure quotas, budget alerts, and rate limits so tests cannot spawn runaway resources.
- Isolate staging and production by project/service accounts/datasets; never use real customer names/data in the lab.

When integrating external payment gateways or logistics providers, evaluate API gateways, egress policies, OAuth/API key handling, allowlists, and webhook signature verification. An external HTTPS endpoint is not automatically trustworthy just because it uses TLS.

## 19. Optimizing Latency and Cost

| Component | Cost Driver | Optimization |
|---|---|---|
| Workflows | Step executions and retries | Avoid redundant steps, set explicit `max_retries`, no tight polling |
| Cloud Run | Requests, CPU/memory, startup, concurrency | Right-size, bound instances to Firestore throughput |
| Firestore | Document reads/writes, storage, indexes | Keep transactions short, avoid excessive contention on hot documents |
| Logging/Monitoring | Log volume, metrics, retention | Log essential metadata, use controlled sampling |
| Future external APIs | Transaction fees or provider billing | Enforce idempotency, timeouts, and reconciliation |

Never raise Workflows retries from 3 to 100 to "fix" a 422 error. Retries must distinguish transient faults from business errors; otherwise steps, load, and cost climb without improving success rates.

A useful KPI:

\[
CostPerSuccessfulOrder =
\frac{WorkflowsCost + CloudRunCost + FirestoreCost + RelatedCosts}
{NumberOfConfirmedOrders}
\]

Factor in costs of cancelled orders, compensation, and operational support when modeling full unit economics.

## 20. Verification and Troubleshooting

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Workflow calls Cloud Run with 401/403 | Wrong OIDC audience or missing `run.invoker` | Check service URL, workflow SA, and Cloud Run IAM |
| Cloud Run 500 querying Firestore | Missing database, missing `datastore.user`, or bad config | Cloud Run logs, Firestore database, and runtime SA |
| Workflow compile error | YAML/Workflows expression syntax or indentation error | Check `steps`/`try`/`retry`/`except` and expressions |
| API returns 409 `IDEMPOTENCY_CONFLICT` | Same `order_id` with different payload | Use a fresh ID or keep payload identical |
| Request retried more than expected | Retries stacked at multiple layers, unclear retry budget | Compare Workflows retries, HTTP client retries, and backend logs |
| Compensation returns 409 | Order already `CONFIRMED` or lingering side effect | GET order; never force-cancel |
| Order stuck `PENDING` too long | Execution died, compensation not durably persisted | Add production journal/reconciler |
| Negative stock or duplicate reservation | Missing transaction or missing idempotency | Check Firestore transactions and per-order keys |
| Execution `SUCCEEDED` yet order failed | Workflow returned `COMPENSATED` as business output | Read `result.status` and emit business metrics |
| Tests collide with old data | Reused `order_id`/`sku` or shared lab instance | Use unique IDs and inspect payloads |

### Final Test Matrix

| Case | Condition | Expected Result |
|---|---|---|
| H1 | All forward calls succeed | `CONFIRMED`, stock deducted once |
| R1 | Charge returns 503 once | Retried, `CHARGED` once, `CONFIRMED` |
| C1 | Shipping returns 422 | `COMPENSATED`; `REFUNDED`/`RELEASED`/`CANCELLED` |
| C2 | Reserve returns 409 `OUT_OF_STOCK` | Not charged; order `CANCELLED`; other orders unaffected |
| I1 | Re-send same `order_id`/payload | No extra deduction or charge |
| I2 | Re-send same ID with different payload | 409 `IDEMPOTENCY_CONFLICT` |
| S1 | Caller lacks `run.invoker` | Cannot call private API |
| U1 | Finalize committed but response lost | No blind refund/cancel; reconciliation |

Tests H1/R1/C1/C2/I1 can be run directly with the demo code. Test U1 requires fault injection right after commit or controlled network mocking; the demo does not automate that case yet.

## 21. Cleaning Up Resources

Once execution logs and test results are saved, delete unused lab components:

~~~bash
gcloud workflows delete orders-saga \
  --location="$REGION" \
  --project="$PROJECT_ID"

gcloud run services delete orders-saga-api \
  --region="$REGION" \
  --project="$PROJECT_ID"
~~~

Firestore documents and container images/build artifacts may still exist and incur charges. Only delete the database, project, or Artifact Registry repository if those resources are **dedicated solely to this lab**, backed up/verified, and contain no data from other work. Deleting the project is not an automated step run by this guide.

## 22. Extension Path

To evolve the lab into a production Java/Spring Boot system:

1. Split endpoints into dedicated Order Service, Inventory Service, Payment Adapter, and Shipping Service, each owning its own data.
2. Run Java/Spring services on Cloud Run or GKE, using Workflows as the Saga orchestrator for long-running flows, branching, and compensation.
3. Add a transactional outbox for events, consumer inbox/dedup, event versioning, and dead-letter handling.
4. Build a Saga journal/lease/fencing mechanism and a recovery worker to resolve `COMPENSATION_PENDING` after restarts.
5. Separate real authorization/capture/refund flows, designing timeouts and `UNKNOWN` states with the payment gateway.
6. Validate consistency, race conditions, cancellation eligibility, and data protection compliance.
7. Run failure-injection tests in staging, never injecting faults via production user requests.
8. Set per-step SLOs, compensation backlog dashboards, and cost-per-successful-order tracking.

## 23. Conclusion

A reliable order-processing workflow is more than "calling several APIs in sequence". It requires idempotency for retries, durable business state, explicit compensating actions, distinction between transient and non-retryable errors, and clear procedures when outcomes are uncertain.

Google Cloud Workflows fits step orchestration and retry policies well; Cloud Run executes each participant's logic; Firestore stores state with local transactions. However, **a Saga is not a distributed ACID transaction**, and a `COMPENSATED` outcome does not instantaneously erase external effects. Production deployments need journals, ownership/fencing, reconciliation, security controls, and operational rigor to ensure final outcomes uphold business contracts.

## References

- [Workflows overview](https://docs.cloud.google.com/workflows/docs/overview)
- [Workflows syntax reference](https://docs.cloud.google.com/workflows/docs/reference/syntax)
- [Retry workflow steps](https://docs.cloud.google.com/workflows/docs/reference/syntax/retrying)
- [Catch workflow errors](https://docs.cloud.google.com/workflows/docs/reference/syntax/catching-errors)
- [Authenticate from Workflows to Cloud Run](https://docs.cloud.google.com/workflows/docs/authenticate-from-workflow)
- [Deploy a workflow with gcloud](https://docs.cloud.google.com/sdk/gcloud/reference/workflows/deploy)
- [Run a workflow and wait](https://docs.cloud.google.com/sdk/gcloud/reference/workflows/run)
- [Use environment variables in Workflows](https://docs.cloud.google.com/workflows/docs/use-environment-variables)
- [Deploy Cloud Run from source](https://docs.cloud.google.com/run/docs/deploying-source-code)
- [Cloud Run authentication and IAM](https://docs.cloud.google.com/run/docs/securing/managing-access)
- [Manage Firestore databases](https://docs.cloud.google.com/firestore/native/docs/manage-databases)
- [Firestore transactions and batched writes](https://docs.cloud.google.com/firestore/native/docs/manage-data/transactions)
- [Cloud Monitoring overview](https://docs.cloud.google.com/monitoring/docs)
