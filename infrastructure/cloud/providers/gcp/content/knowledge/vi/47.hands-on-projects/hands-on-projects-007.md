# Dự án workflow xử lý đơn hàng có retries và compensation

## 1. Mục tiêu và bối cảnh

Một ứng dụng thương mại điện tử phải thực hiện nhiều bước khi khách hàng đặt hàng: tiếp nhận yêu cầu, giữ hàng trong kho, xác nhận thanh toán, đặt vận chuyển và hoàn tất đơn. Nếu thanh toán thành công nhưng đặt vận chuyển thất bại, việc trả lỗi HTTP cho người mua **không tự hoàn trả tiền và số lượng hàng đã giữ**. Nếu kết nối bị ngắt ngay sau khi trừ hàng, retry không có idempotency có thể trừ hàng hai lần. Những vấn đề này càng dễ xuất hiện khi các bước nằm ở những dịch vụ hoặc project khác nhau.

Dự án thực hành này xây dựng một **Saga được điều phối (orchestrated Saga)** trên Google Cloud:

- **Google Cloud Workflows** điều phối các bước, đặt timeout, retry có giới hạn và gọi các thao tác hoàn tác.
- **Cloud Run** chạy một API mô phỏng các thành phần Order, Inventory, Payment và Shipping. Để bài thực hành gọn, các endpoint nằm trong **một** Cloud Run service, nhưng giữ ranh giới nghiệp vụ rõ ràng.
- **Firestore in Native mode** lưu trạng thái đơn hàng và số lượng tồn kho. Transaction giúp bảo vệ một số thay đổi trạng thái trước các yêu cầu đồng thời.
- **IAM và OIDC** bảo vệ Cloud Run; Workflows gọi service bằng danh tính service account.
- **Cloud Logging/Monitoring** cung cấp tín hiệu để kiểm tra tiến độ, lỗi retry và compensation.

Đây là bài thực hành của module CLOUD_PROVIDERS_GCP, liên hệ từ project, IAM, Cloud Run và cơ sở dữ liệu tới tự động hóa phát hành, độ tin cậy và chi phí. Mã Payment chỉ **mô phỏng** thu và hoàn tiền bằng trạng thái Firestore; **không** kết nối cổng thanh toán, không thu tiền thực và chưa phải thiết kế được phép sử dụng cho giao dịch tài chính production.

Kết thúc dự án, bạn phải:

1. Khởi chạy được một workflow với đơn hàng hợp lệ và nhận trạng thái CONFIRMED.
2. Chứng minh lỗi tạm thời HTTP 503 được retry mà không ghi thanh toán hai lần.
3. Chứng minh lỗi đặt vận chuyển HTTP 422 kích hoạt compensation theo thứ tự ngược.
4. Xem được trạng thái đơn hàng sau khi hoàn tác và xác nhận tồn kho được phục hồi.
5. Phân biệt retry, compensation, transaction cục bộ và giao dịch phân tán.
6. Biết các kiểm soát phải bổ sung trước khi chuyển bài demo thành hệ thống production.

## 2. Thành phẩm và tiêu chí nghiệm thu

| Thành phẩm | Minh chứng cần thu |
|---|---|
| Cloud Run API riêng tư | URL service, trạng thái triển khai, không cho allUsers gọi |
| Firestore database | Collection orders và stock chứa trạng thái sau khi workflow chạy |
| Workflow orders-saga | Đã deploy thành công, có execution history |
| Happy path | Đơn CONFIRMED, inventory RESERVED, payment CHARGED, shipment BOOKED |
| Transient-failure test | Request thanh toán đầu tiên 503, lần sau thành công; chỉ có một hiệu ứng CHARGED |
| Business-failure test | Shipping 422, payment REFUNDED, inventory RELEASED, order CANCELLED |
| Duplicate test | Gửi lại cùng order_id/payload không trừ hàng hoặc thu tiền lần nữa |
| Log và báo cáo | Execution ID, order ID, lỗi theo từng bước, kết quả compensation |

Trạng thái CHARGED/REFUNDED trong demo chỉ là nhãn dữ liệu, không phải kết quả đối soát với một payment provider thật.

## 3. Kiến trúc và trình tự xử lý

~~~mermaid
flowchart LR
    U[Client / kiểm thử] --> W[Google Cloud Workflows]
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

Luồng thành công:

~~~mermaid
sequenceDiagram
    participant W as Workflows
    participant A as Cloud Run API
    participant D as Firestore
    W->>A: POST /orders (idempotency = order_id)
    A->>D: Tạo đơn PENDING nếu chưa có
    W->>A: POST /orders/{id}/reserve
    A->>D: Giảm tồn kho một lần
    W->>A: POST /orders/{id}/charge
    A->>D: Đánh dấu CHARGED một lần
    W->>A: POST /orders/{id}/ship
    A->>D: Đánh dấu BOOKED một lần
    W->>A: POST /orders/{id}/confirm
    A->>D: Chuyển order thành CONFIRMED
    A-->>W: Hoàn tất
~~~

Khi bước sau thất bại, các thao tác bù trừ được gọi **ngược thứ tự**:

~~~mermaid
flowchart TD
    X[Lỗi sau khi đã bắt đầu Saga] --> A[Cancel shipment, nếu có]
    A --> B[Refund payment, nếu đã charge]
    B --> C[Release inventory, nếu đang reserve]
    C --> D[Cancel order nếu trạng thái cho phép]
    D --> E{Mọi compensation thành công?}
    E -->|Có| F[COMPENSATED]
    E -->|Không| G[COMPENSATION_PENDING và đối soát]
~~~

Điểm quan trọng: Workflows **không thể rollback một transaction đã commit ở dịch vụ khác**. Mỗi bước phải cung cấp một hành động hoàn tác có ngữ nghĩa riêng. Refund là một giao dịch mới; release inventory là thao tác tăng lại tồn kho có điều kiện; cancel shipment có thể thất bại nếu hàng đã giao.

## 4. Định nghĩa nghiệp vụ, lỗi và trạng thái

### Các bước và thao tác hoàn tác

| Forward action | Thành công | Compensation | Bảo đảm mong muốn |
|---|---|---|---|
| Create order | PENDING | Cancel order | Cùng order_id + payload chỉ tạo một lần |
| Reserve inventory | RESERVED | Release inventory | Không trừ/tăng cùng reservation hai lần |
| Charge payment (mô phỏng) | CHARGED | Refund payment | Idempotency key gắn với order và loại thao tác |
| Book shipment | BOOKED | Cancel shipment | Hủy khi chưa ở trạng thái không thể hủy |
| Confirm order | CONFIRMED | Không tự hoàn tác sau xác nhận | Đây là ranh giới commit nghiệp vụ của demo |

### Phân loại lỗi

- **Transient:** 429/502/503/504, mất kết nối hoặc timeout; retry khi thao tác được thiết kế idempotent.
- **Business/permanent:** hết hàng 409, địa chỉ không hợp lệ 422, quyền truy cập 403; không retry vô hạn.
- **Unknown outcome:** response bị mất sau khi server commit. Không được tự suy ra request chưa chạy; cần idempotency và khả năng đọc trạng thái.
- **Compensation failure:** hoàn tác không thành công sau số lần retry giới hạn; giữ trạng thái COMPENSATION_PENDING và cần quy trình phục hồi.

Trong demo, một order sau khi CONFIRMED **không thể** bị cancel/refund/release bằng các endpoint compensation. Nếu xác nhận thành công nhưng Workflows mất response, compensation sẽ bị chặn; hệ thống phải **đối soát trạng thái** thay vì hoàn tiền một đơn đã xác nhận. Trong hệ thống thật, “đã giao hàng” hoặc “đã thanh toán” có thể tạo các ranh giới nghiệp vụ mạnh hơn.

### Idempotency và retry

Đặt một order_id ổn định từ request gốc, không tạo ID mới mỗi lần retry. Phía server so sánh payload của yêu cầu trùng và trả lỗi 409 nếu cùng ID nhưng khác nội dung. Mỗi bước cập nhật trạng thái bằng Firestore transaction; nếu state đã là kết quả mong muốn thì trả 200 mà không thực hiện lại hiệu ứng.

Workflows chỉ retry một thao tác POST khi **contract của chính endpoint đó** đã bảo đảm idempotency. Không gắn mặc định retry idempotent cho mọi POST trên hệ thống production.

## 5. Chuẩn bị Google Cloud và quyền truy cập

### Điều kiện đầu vào

- Một Google Cloud project thử nghiệm riêng có billing được bật và bạn có quyền triển khai.
- Google Cloud CLI đã đăng nhập, Python 3 phù hợp và terminal Bash (Cloud Shell có thể dùng).
- Quyền bật APIs, quản lý service accounts/IAM, tạo Cloud Run, Workflows và Firestore.
- Ngân sách/alert cho project để tránh tài nguyên chạy ngoài dự kiến.

Ví dụ chọn project và region (thay bằng giá trị của bạn):

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

Tạo hai service accounts tách biệt:

~~~bash
gcloud iam service-accounts create saga-api-sa \
  --display-name="Order saga Cloud Run runtime"

gcloud iam service-accounts create saga-workflow-sa \
  --display-name="Order saga Workflows identity"
~~~

Cloud Run runtime cần đọc/ghi Firestore. Với bài lab sử dụng một database và project riêng, có thể dùng role sau ở project scope; trong production nên giảm phạm vi bằng IAM Conditions/custom roles và phân vùng môi trường thích hợp:

~~~bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$RUN_SA" \
  --role="roles/datastore.user"
~~~

### Tạo Firestore database

Nếu project **chưa có** database mặc định:

~~~bash
gcloud firestore databases create \
  --database="(default)" \
  --location="$REGION" \
  --edition=standard \
  --type=firestore-native
~~~

Kiểm tra database đã tồn tại trước khi chạy lệnh tạo; không xóa database đang chứa dữ liệu. Firestore location không thể tùy ý đổi sau khi tạo. Demo dùng Firestore Server SDK và service account IAM, không dùng Firebase client SDK trực tiếp từ trình duyệt.

## 6. Tổ chức mã ứng dụng mẫu

Trong thư mục demo **trên máy người học** (không phải thư mục tài liệu của module này), tạo ba file:

~~~text
orders-saga-lab/
  main.py
  requirements.txt
  Procfile
  workflow.yaml
~~~

Nội dung requirements.txt:

~~~text
Flask>=3,<4
google-cloud-firestore>=2,<3
gunicorn>=22,<25
~~~

Nội dung Procfile:

~~~text
web: gunicorn --bind :$PORT main:app
~~~

Ví dụ dùng các khoảng phiên bản để minh họa; hệ thống thật cần khóa dependency versions và quét lỗ hổng trong CI. Ứng dụng sử dụng một Cloud Run service cho thuận tiện thực hành, không phải kiến trúc triển khai bắt buộc.

## 7. Cloud Run API: ghi trạng thái idempotent bằng Firestore

### Nguyên tắc thiết kế

Các endpoint cung cấp những contract đơn giản:

- POST /orders: tạo order, dùng order_id như idempotency key.
- POST /orders/{id}/reserve: giảm tồn kho nếu chưa giữ.
- POST /orders/{id}/charge: đánh dấu payment CHARGED.
- POST /orders/{id}/ship: đánh dấu shipment BOOKED.
- POST /orders/{id}/confirm: đánh dấu CONFIRMED nếu mọi bước hoàn tất.
- POST /orders/{id}/cancel-shipment, /refund, /release, /cancel: compensation.
- GET /orders/{id}: kiểm tra trạng thái sau khi Workflows kết thúc.

Mỗi request có thể được gọi lại nhiều lần. Dữ liệu demo lưu trong Firestore:

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

Trường fail_payment_once và fail_shipping **chỉ dùng để tiêm lỗi trong lab**. Không chấp nhận tham số điều khiển hành vi lỗi từ khách hàng ở production.

### Mã main.py (ứng dụng mẫu có thể chạy)

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
            # Compensation trước khi order được tạo phải là no-op.
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
            # Một execution trùng chỉ được xác nhận những bước đã làm.
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

### Giới hạn của mã demo

- Tồn kho ban đầu được giả lập là 10 đơn vị khi SKU lần đầu được sử dụng; production phải quản lý inventory qua nghiệp vụ nhập kho riêng.
- Dữ liệu tồn kho và đơn hàng cùng Firestore nên transaction bảo đảm tính nguyên tử **trong Firestore**. Khi tách Inventory, Payment và Shipping thành dịch vụ/database độc lập, **không có transaction chung**; phải áp dụng Saga thực sự và outbox/inbox hoặc journal bền vững.
- Tác vụ hoàn tiền trong demo chỉ cập nhật một trường. Với payment provider thực, cần idempotency key riêng, đối soát charge/refund và xử lý cả phản hồi không xác định.
- Hai Workflows executions dùng cùng order_id có thể xen kẽ giữa các bước; demo ngăn một số tác động trùng bằng transaction nhưng chưa có **lease/fencing theo execution_id** để đảm bảo chỉ một coordinator điều khiển một order tại một thời điểm.
- Cloud Run Invoker IAM bảo vệ cả service, chưa có RBAC riêng từng endpoint. Trong production cần tách quyền admin, operator và service-to-service.
- Không được dùng lab để xử lý tiền, hàng hóa hoặc dữ liệu khách hàng thật.

## 8. Triển khai Cloud Run API riêng tư

Từ thư mục orders-saga-lab chứa main.py, requirements.txt và Procfile:

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

Triển khai từ source cần thêm các quyền Cloud Build/Artifact Registry và Service Account User cho tài khoản triển khai, theo hướng dẫn Cloud Run hiện hành. Lệnh tạo service có thể phát sinh chi phí xây dựng và vận hành.

Cho phép Workflows service account gọi riêng service này:

~~~bash
gcloud run services add-iam-policy-binding orders-saga-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --member="serviceAccount:$WORKFLOW_SA" \
  --role="roles/run.invoker"
~~~

Không cấp allUsers quyền run.invoker để tiện test. Người chạy gcloud Workflows cần quyền triển khai và thực thi Workflows; người dùng gọi trực tiếp Cloud Run để GET trạng thái cần được cấp quyền invoker riêng.

## 9. Định nghĩa Workflows với retry và compensation

Workflows gọi Cloud Run bằng HTTP POST và xác thực OIDC. Biến API_BASE_URL được cấu hình khi deploy, không truyền từ đầu vào người dùng. Mỗi endpoint POST trong demo có contract idempotent, vì vậy dùng default retry predicate dành cho thao tác idempotent với 3 lần retry sau lần gọi đầu. Chính sách này có thể retry lỗi kết nối/timeout và HTTP 429, 502, 503, 504; các lỗi nghiệp vụ 409/422 không được retry.

Nội dung workflow.yaml:

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

            # Compensation chạy ngược thứ tự và không dừng ở lỗi đầu tiên.
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

### Vì sao compensation gọi cả các bước chưa thực hiện?

Sau một timeout, Workflows có thể không biết endpoint đã thực hiện side effect hay chưa. Vì vậy demo gọi các thao tác bù trừ theo thứ tự ngược **bất kể response của bước forward đã được nhận hay chưa**. Mỗi compensation kiểm tra Firestore state: nếu chưa từng book/charge/reserve thì trả no-op; nếu đã thực hiện thì hoàn tác đúng một lần.

Đây là lựa chọn **đơn giản hóa trong lab**. Với hệ thống thật, mỗi participant cần contract rõ về operation status, cancellation eligibility, idempotency scope và thứ tự compensation. Không thể tùy tiện gọi refund trước khi biết giao dịch đã xảy ra, nhất là với payment provider bên ngoài.

### Tại sao không trả HTTP 500 khi compensation hoàn tất?

Trong bài lab, Workflows trả kết quả có trường status là COMPENSATED hoặc COMPENSATION_PENDING để dễ quan sát. Một Workflows execution có thể ở trạng thái SUCCEEDED mặc dù **đơn hàng thất bại về nghiệp vụ**. Production phải xuất business outcome metric, sự kiện hoặc bảng job state riêng và cảnh báo khi compensation_pending không rỗng, không chỉ quan sát execution status.

## 10. Deploy workflow và gán quyền

Giữ URL API ở cấu hình của workflow thay vì tin một URL do người dùng truyền lên:

~~~bash
gcloud workflows deploy orders-saga \
  --source=workflow.yaml \
  --location="$REGION" \
  --project="$PROJECT_ID" \
  --service-account="$WORKFLOW_SA" \
  --set-env-vars="API_BASE_URL=$API_BASE_URL"
~~~

Người triển khai cần quyền tạo/cập nhật workflow và quyền actAs service account; người chạy Workflows cần quyền thực thi, ví dụ roles/workflows.invoker hoặc quyền tương đương phù hợp.

Các call trong workflow dùng OIDC audience là **base URL của Cloud Run**, không phải URL đầy đủ kèm /orders/...; điều này quan trọng khi service yêu cầu xác thực. Cloud Run runtime service account và Workflows service account là hai danh tính khác nhau.

## 11. Kiểm thử kịch bản 1: happy path

Chạy:

~~~bash
gcloud workflows run orders-saga \
  --location="$REGION" \
  --project="$PROJECT_ID" \
  --data='{"order_id":"demo-success-001","sku":"sku-success-001","quantity":2,"amount_cents":2500,"fail_payment_once":false,"fail_shipping":false}'
~~~

Kết quả mong đợi ở phần result:

~~~json
{
  "order_id": "demo-success-001",
  "status": "CONFIRMED",
  "pending": []
}
~~~

Kiểm tra order bằng tài khoản được cấp quyền Cloud Run Invoker:

~~~bash
curl -fsS \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "$API_BASE_URL/orders/demo-success-001"
~~~

Trạng thái mong đợi: status CONFIRMED, inventory_state RESERVED, payment_state CHARGED, shipping_state BOOKED. Với SKU mới, giả lập stock ban đầu 10, reserve quantity=2 nên còn 8. Tài khoản chạy curl cần quyền gọi Cloud Run private service; nhận 403 không có nghĩa Workflows đã lỗi.

## 12. Kiểm thử kịch bản 2: retry lỗi 503 tạm thời

Đặt fail_payment_once=true để endpoint charge tạo đúng một phản hồi HTTP 503 trước khi ghi CHARGED:

~~~bash
gcloud workflows run orders-saga \
  --location="$REGION" \
  --project="$PROJECT_ID" \
  --data='{"order_id":"demo-retry-001","sku":"sku-retry-001","quantity":2,"amount_cents":2500,"fail_payment_once":true,"fail_shipping":false}'
~~~

Kết quả mong đợi vẫn là CONFIRMED. GET order phải cho thấy:

~~~json
{
  "order_id": "demo-retry-001",
  "payment_failure_injected": true,
  "payment_state": "CHARGED",
  "status": "CONFIRMED"
}
~~~

Đây là **một phần** các trường trong document, không phải toàn bộ response. Cờ payment_failure_injected chứng minh lời gọi đầu đã gặp lỗi được tiêm và lần sau hoàn tất. Khi xem execution history, bạn có thể thấy việc thử lại charge_payment theo cấu hình retry.

Chạy lại **cùng payload và order_id**:

~~~bash
gcloud workflows run orders-saga \
  --location="$REGION" \
  --project="$PROJECT_ID" \
  --data='{"order_id":"demo-retry-001","sku":"sku-retry-001","quantity":2,"amount_cents":2500,"fail_payment_once":true,"fail_shipping":false}'
~~~

Các endpoint nhìn thấy trạng thái đã đạt và trả ALREADY_DONE hoặc ALREADY_CONFIRMED; tồn kho không bị trừ thêm. Cùng order_id mà đổi quantity/amount_cents phải nhận IDEMPOTENCY_CONFLICT (409), không nên tạo “phiên bản đơn hàng mới” bằng cách âm thầm ghi đè payload.

## 13. Kiểm thử kịch bản 3: shipping thất bại và compensation

Tạo SKU riêng và bật fail_shipping=true:

~~~bash
gcloud workflows run orders-saga \
  --location="$REGION" \
  --project="$PROJECT_ID" \
  --data='{"order_id":"demo-compensate-001","sku":"sku-compensate-001","quantity":3,"amount_cents":4000,"fail_payment_once":false,"fail_shipping":true}'
~~~

Trình tự kỳ vọng:

1. Order PENDING được tạo.
2. Inventory RESERVED, stock giảm 10 xuống 7.
3. Payment CHARGED.
4. Shipping trả 422 (lỗi nghiệp vụ, không retry).
5. Cancel shipment là no-op vì chưa BOOKED.
6. Refund chuyển CHARGED → REFUNDED.
7. Release inventory chuyển RESERVED → RELEASED; stock tăng lại 10.
8. Cancel order chuyển PENDING → CANCELLED.
9. Workflow trả COMPENSATED và pending rỗng.

Kết quả minh họa:

~~~json
{
  "order_id": "demo-compensate-001",
  "status": "COMPENSATED",
  "pending": [],
  "failure": "HTTP server responded with error code 422"
}
~~~

Nội dung field failure thực tế phụ thuộc error map. Kiểm tra Firestore order phải cho thấy **status CANCELLED, inventory_state RELEASED, payment_state REFUNDED, shipping_state NONE**. Dữ liệu tồn kho cho SKU mới phải trở về 10. Workflows không sửa lại quá khứ của charge; nó tạo hành động hoàn tác tường minh.

## 14. Kiểm thử kịch bản 4: lỗi ở bước sớm

Trong demo tồn kho mỗi SKU bắt đầu là 10. Đặt quantity=10 cho một order có SKU mới, sau đó dùng một order khác với cùng SKU (ví dụ 2 đơn vị) để gây hết hàng:

~~~bash
# Đầu tiên giữ toàn bộ 10 đơn vị SKU shared-demo.
gcloud workflows run orders-saga \
  --location="$REGION" --project="$PROJECT_ID" \
  --data='{"order_id":"demo-stock-keeper","sku":"shared-demo","quantity":10,"amount_cents":1000}'

# Đơn tiếp theo không thể reserve.
gcloud workflows run orders-saga \
  --location="$REGION" --project="$PROJECT_ID" \
  --data='{"order_id":"demo-out-of-stock","sku":"shared-demo","quantity":2,"amount_cents":1000}'
~~~

Lời gọi reserve của đơn thứ hai trả 409 OUT_OF_STOCK. Workflows không nên retry lỗi nghiệp vụ này; compensation của order thứ hai chỉ làm các thao tác không có gì để hoàn tác rồi CANCELLED. Nó **không** được giải phóng inventory thuộc đơn demo-stock-keeper. Tồn kho shared-demo vẫn bằng 0.

## 15. Thiết kế xử lý compensation chưa hoàn tất

Không phải compensation nào cũng thành công. Ví dụ payment provider đã ghi charge nhưng lỗi hệ thống khiến refund không thể hoàn tất trong vài phút. Không được:

- Báo order CANCELLED hoàn toàn nếu payment vẫn CHARGED.
- Tiếp tục thực hiện đơn hàng mới dùng cùng reservation chưa rõ trạng thái.
- Retry refund vô hạn hoặc phát hành nhiều lệnh refund với ID mới.
- Xóa order record vì tưởng workflow đã kết thúc.

### Trạng thái đề xuất

| State | Ý nghĩa | Hành động |
|---|---|---|
| CONFIRMED | Các bước forward đã xác nhận | Kết thúc; chỉ hoàn/đổi theo quy trình nghiệp vụ riêng |
| COMPENSATED | Các hành động hoàn tác đã thành công hoặc no-op | Kết thúc thất bại có kiểm soát |
| COMPENSATION_PENDING | Ít nhất một thao tác bù trừ chưa xác minh được | Cần recovery worker/queue và alert |
| RECONCILIATION_REQUIRED | Không chắc kết quả thực tế của bước, hoặc finalize có thể đã thành công | Kiểm tra nguồn sự thật rồi quyết định |

Trong workflow.yaml demo, khi một compensation thất bại sau retry, tên thao tác được thêm vào compensation_pending và workflow tiếp tục thử các bước bù trừ khác. Endpoint cancel_order từ chối khi còn payment CHARGED, shipment BOOKED hoặc inventory RESERVED. Như vậy, một lần refund lỗi không khiến order được đánh dấu CANCELLED sai. Tuy nhiên, trạng thái COMPENSATION_PENDING **chỉ nằm trong kết quả execution** nếu hệ thống chưa bổ sung job ledger/worker phục hồi.

### Kế hoạch production cho thao tác bù trừ

1. Lưu Saga ID, execution ID, step state và idempotency key trong bảng journal bền vững.
2. Ghi deadline, số lần retry, last error, next retry time và owner.
3. Dùng Cloud Tasks hoặc queue/worker phục hồi để retry compensation có giới hạn.
4. Tra cứu trạng thái hiện tại từ participant trước mỗi lần retry.
5. Có hàng đợi lỗi và quy trình can thiệp thủ công khi hết budget.
6. Chỉ báo completed sau khi xác minh toàn bộ effects không còn cần hoàn tác.
7. Không auto-compensate một order đã CONFIRMED khi chỉ mất response finalize.

Điều quan trọng nhất là **unknown outcome không đồng nghĩa failed outcome**. Trước một khoản refund hoặc cancellation khó đảo ngược, cần reconciliation với nguồn dữ liệu gốc.

## 16. Tránh race condition và chạy trùng workflow

Firestore transaction trong demo giúp các operation của cùng order không cập nhật trạng thái chồng lấn một cách mù quáng. Nhưng Saga thực tế cần thêm:

- **Execution lease:** chỉ một coordinator sở hữu order trong một thời điểm, có TTL và fencing token.
- **Step journal:** trạng thái NOT_STARTED, STARTED, SUCCEEDED, FAILED, COMPENSATING, COMPENSATED.
- **Stable idempotency key:** ví dụ order_id + action + version, áp cả cho payment provider.
- **Outbox/inbox:** ghi trạng thái và event trong cùng transaction cục bộ; phát sự kiện sau đó với de-duplication.
- **Monotonic transitions:** trạng thái đã CONFIRMED không thể quay ngược về PENDING.
- **Reconciliation job:** tìm các order không đổi trạng thái quá lâu, đối chiếu payment, inventory, shipment.

Hai workflow cùng order_id có thể thực hiện các bước xen kẽ: một execution đang charge trong khi execution khác gặp lỗi và bắt đầu refund. Idempotent endpoint là cần thiết, nhưng **chưa đủ** để bảo đảm trật tự Saga. Với production, thêm owner token và từ chối lệnh mang token cũ ở từng participant.

## 17. Quan sát và đo độ tin cậy

### Log và correlation

Log nên chứa: order_id, saga_id, execution_id, step, attempt, error code, idempotency key dạng không nhạy cảm, compensation state và duration. Tránh log số thẻ, token, địa chỉ khách hàng hoặc dữ liệu thanh toán.

Cloud Logging và Workflows execution history có thể giúp quan sát đường chạy. Ở ứng dụng production, nên xuất OpenTelemetry traces và metric nghiệp vụ, tránh chỉ xem Workflows SUCCEEDED/FAILED.

### SLI/SLO gợi ý

| SLI | Định nghĩa | Mục tiêu minh họa |
|---|---|---|
| Order completion ratio | Số đơn CONFIRMED / số đơn hợp lệ bắt đầu | Theo mục tiêu sản phẩm |
| Saga duration p95/p99 | Thời gian từ start tới terminal state | p95 dưới 10 giây trong bài demo |
| Retry rate | Số retry / số bước có gọi API | Phát hiện dependency bất ổn |
| Compensation success ratio | Số Saga hoàn tác đủ / số Saga cần hoàn tác | Tiệm cận 100%; có alert cho tồn đọng |
| Compensation backlog age | Tuổi các order COMPENSATION_PENDING | Alert vượt thời hạn đã cam kết |
| Duplicate suppression | Số yêu cầu trùng được dedup đúng | Không có double charge/reserve |
| Business-error breakdown | OUT_OF_STOCK, SHIPPING_ADDRESS_REJECTED... | Hỗ trợ cải tiến nghiệp vụ |

Các con số chỉ minh họa; không áp dụng p95 10 giây cho quy trình vận chuyển thực tế. Workflows tính phí theo số bước và loại thực thi; retry cũng làm tăng số bước được tính, nên cần giới hạn retry/backoff và tránh polling quá dày.

## 18. Quyền tối thiểu và an toàn trong production

- Cloud Run private, chỉ service account được cấp roles/run.invoker mới gọi được.
- Workflow service account không cần roles/editor hay quyền Firestore trực tiếp.
- Cloud Run runtime service account chỉ nhận quyền dữ liệu cần dùng; lab cấp datastore.user ở project riêng.
- Người chạy execution chỉ cần quyền Workflows cần thiết, không được tự chỉnh URL đích hoặc workflow definition.
- Không đưa API keys và payment secrets vào workflow source; dùng Secret Manager và quyền giới hạn khi thật sự cần.
- Mỗi participant có validation ở server, không dựa duy nhất vào thông số của client.
- Thiết lập quota, budget alert và rate limit để test không tạo tài nguyên ngoài ý muốn.
- Tách staging và production bằng project/service accounts/dataset; không dùng tên dữ liệu khách hàng trong lab.

Khi kết nối nhà cung cấp thanh toán hoặc dịch vụ logistics bên ngoài, cân nhắc gateway, egress policies, OAuth/API key handling, allowlist và cơ chế xác minh webhook. Một endpoint HTTPS bên ngoài không tự đáng tin vì nó có TLS.

## 19. Tối ưu độ trễ và chi phí

| Thành phần | Nguồn chi phí | Cách tối ưu |
|---|---|---|
| Workflows | Bước thực thi và retry | Hạn chế bước thừa, max_retries rõ, không polling dày |
| Cloud Run | Requests, CPU/memory, startup, concurrency | Right-size, giới hạn số instance theo sức chịu của Firestore |
| Firestore | Document reads/writes, storage, index | Giữ transaction ngắn, tránh đọc/ghi cùng hot document quá mức |
| Logging/Monitoring | Dữ liệu ghi log, metric và retention | Log metadata cần thiết, sampling có kiểm soát |
| External APIs tương lai | Phí giao dịch hoặc provider billing | Dùng idempotency, timeout và reconciliation |

Không tăng Workflows retry từ 3 lên 100 để “chữa” một lỗi 422. Retry phải phân biệt lỗi tạm thời và lỗi nghiệp vụ; nếu không, số bước, tải và chi phí sẽ tăng mà không nâng tỷ lệ thành công.

Một KPI hữu ích:

\[
CostPerSuccessfulOrder =
\frac{WorkflowsCost + CloudRunCost + FirestoreCost + RelatedCosts}
{NumberOfConfirmedOrders}
\]

Tính thêm chi phí xử lý đơn bị hủy, bù trừ và hỗ trợ vận hành nếu muốn ước lượng đầy đủ unit economics.

## 20. Kiểm chứng và troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Workflow gọi Cloud Run 401/403 | OIDC audience sai hoặc thiếu run.invoker | Kiểm tra service URL, workflow SA và Cloud Run IAM |
| Cloud Run 500 khi truy vấn Firestore | Chưa có database, thiếu datastore.user hoặc config sai | Cloud Run logs, Firestore database và runtime SA |
| Workflow compile lỗi | Sai cú pháp YAML/Workflows expression hoặc thụt dòng | Kiểm tra steps/try/retry/except và expression |
| API trả 409 IDEMPOTENCY_CONFLICT | Cùng order_id nhưng payload khác | Dùng ID mới hoặc giữ nguyên payload |
| Một request bị retry nhiều hơn dự kiến | Retry ở nhiều tầng, retry budget không rõ | So sánh Workflows retries, HTTP client retries và backend logs |
| Compensation trả 409 | Order đã CONFIRMED hoặc còn side effect chưa dọn | GET order; không cưỡng bức cancel |
| Order bị giữ PENDING quá lâu | Execution chết, compensation không được lưu bền | Thêm journal/reconciler production |
| Stock âm hoặc trùng reservation | Không transaction hoặc thiếu idempotency | Kiểm tra Firestore transaction và key theo order |
| Execution SUCCEEDED nhưng đơn không thành công | Workflow trả COMPENSATED như business result | Đọc result.status và xuất business metrics |
| Test trùng dữ liệu cũ | Dùng lại order_id/sku hoặc instance lab chung | Dùng ID riêng và kiểm tra payload |

### Ma trận kiểm thử cuối cùng

| Case | Điều kiện | Kết quả mong đợi |
|---|---|---|
| H1 | Toàn bộ forward calls thành công | CONFIRMED, tồn kho giảm một lần |
| R1 | Charge trả 503 một lần | Có retry, CHARGED đúng một lần, CONFIRMED |
| C1 | Shipping trả 422 | COMPENSATED; REFUNDED/RELEASED/CANCELLED |
| C2 | Reserve trả 409 OUT_OF_STOCK | Không charge; order CANCELLED; không ảnh hưởng order khác |
| I1 | Gọi lại cùng order_id/payload | Không trừ hàng/thu tiền thêm |
| I2 | Gọi lại cùng ID nhưng payload khác | 409 IDEMPOTENCY_CONFLICT |
| S1 | Tài khoản không có run.invoker | Không gọi được API riêng tư |
| U1 | Finalize đã commit nhưng mất response | Không refund/cancel mù quáng; reconciliation |

Các test H1/R1/C1/C2/I1 có thể thực hiện bằng mã demo. Test U1 cần failure injection ngay sau commit hoặc mock network có kiểm soát; bài demo chưa tự động tạo tình huống này.

## 21. Thu dọn tài nguyên

Khi đã lưu execution logs và kết quả test, xóa các thành phần lab không còn sử dụng:

~~~bash
gcloud workflows delete orders-saga \
  --location="$REGION" \
  --project="$PROJECT_ID"

gcloud run services delete orders-saga-api \
  --region="$REGION" \
  --project="$PROJECT_ID"
~~~

Các documents trong Firestore và các container images/build artifacts có thể vẫn tồn tại và tính phí. Chỉ xóa database, project hoặc Artifact Registry repository nếu đó là tài nguyên **riêng cho bài lab**, đã sao lưu/xác minh và không chứa dữ liệu của công việc khác. Việc xóa project không phải bước tự động được chạy trong tài liệu này.

## 22. Hướng mở rộng

Để phát triển bài lab thành hệ thống Java/Spring Boot production:

1. Tách các endpoint thành Order Service, Inventory Service, Payment Adapter và Shipping Service riêng, mỗi service sở hữu dữ liệu của mình.
2. Dùng Cloud Run hoặc GKE cho các Java/Spring services, và Workflows làm Saga orchestrator khi cần flow dài, branching và compensation.
3. Bổ sung transactional outbox cho sự kiện, inbox/dedup cho consumer, event versioning và dead-letter handling.
4. Tạo Saga journal/lease/fencing và recovery worker để xử lý COMPENSATION_PENDING sau restart.
5. Tách authorization/capture/refund thật, thiết kế timeout và trạng thái UNKNOWN với payment gateway.
6. Kiểm tra consistency, race conditions, cancellation eligibility và tuân thủ bảo vệ dữ liệu.
7. Chạy failure-injection tests trên staging, không tiêm lỗi từ request production của người dùng.
8. Đặt SLO theo từng bước, dashboard compensation backlog và cost per successful order.

## 23. Kết luận

Một workflow xử lý đơn hàng đáng tin cậy không chỉ “gọi lần lượt nhiều API”. Nó cần idempotency cho retry, trạng thái nghiệp vụ bền vững, các hành động compensation rõ ràng, khả năng phân biệt lỗi tạm thời và lỗi không thể retry, cùng quy trình xử lý khi kết quả trả về không chắc chắn.

Google Cloud Workflows rất phù hợp để điều phối các bước và chính sách retry; Cloud Run thực thi logic từng participant; Firestore lưu trạng thái và transaction cục bộ. Tuy nhiên, **Saga không phải distributed ACID transaction** và kết quả COMPENSATED không làm cho mọi tác động bên ngoài biến mất tức thì. Khi triển khai production, cần thêm journal, ownership/fencing, reconciliation, bảo mật và vận hành để bảo đảm các hiệu ứng cuối cùng phù hợp với hợp đồng nghiệp vụ.

## Tài liệu tham khảo

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
