# Firestore database modes và tiêu chí lựa chọn

> **Chương:** Firestore và Firebase  
> **Bài học:** Firestore database modes và tiêu chí lựa chọn  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học khám phá Google Cloud từ project, IAM và VPC tới Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu; đồng thời biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa triển khai, theo dõi độ tin cậy và chi phí. Với ứng dụng Java kết hợp Firebase hoặc Google Cloud, **chọn đúng Firestore database mode** là quyết định kiến trúc ban đầu: nó ảnh hưởng API, SDK, mô hình dữ liệu, truy vấn, bảo mật và cách di chuyển về sau.

Firestore là dịch vụ cơ sở dữ liệu tài liệu NoSQL được quản lý. **Không nên dừng ở so sánh cũ “Native hay Datastore”**: tài liệu Google Cloud hiện hành phân biệt **database edition** (Standard hoặc Enterprise) và **data access mode** (Native, Datastore compatibility hoặc MongoDB compatibility). Hai lựa chọn có quan hệ ràng buộc nhau.

**Kết luận nhanh:** ứng dụng mới dùng Firebase SDK và realtime/offline thường chọn **Firestore Native**; ứng dụng cần Datastore API cũ chọn **Standard + Datastore mode**; ứng dụng muốn dùng MongoDB driver/MQL cân nhắc **Enterprise + MongoDB compatibility**; nếu dùng Native nhưng cần query engine nâng cao/Pipeline operations, đánh giá **Enterprise + Native mode**. Mỗi trường hợp vẫn cần kiểm chứng hiệu năng và tổng chi phí.

Ví dụ dự án, collection, người dùng và cấu hình trong bài đều là giả định. Lệnh `gcloud firestore databases create` có thể tạo dữ liệu tính phí và cấu hình location lâu dài; chỉ chạy trong sandbox được phép. Tài liệu tự chứa nhưng cố ý tập trung vào **tiêu chí lựa chọn**, không thay một hướng dẫn vận hành Firestore toàn diện.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **edition** với **data access mode**, xác định các tổ hợp được hỗ trợ.
2. Mô tả **Firestore in Native mode**, **Firestore in Datastore mode** và **Firestore with MongoDB compatibility**.
3. Giải thích Firestore **Standard vs Enterprise** về query engine, indexing, tính năng realtime/offline và cách tính chi phí.
4. Chọn mode phù hợp cho **mobile/web Firebase**, **Java backend trên Cloud Run/GKE**, **legacy App Engine Datastore** và **MongoDB workloads**.
5. Mô hình hóa dữ liệu tài liệu, thiết kế query và tránh các giả định kiểu quan hệ SQL.
6. Phân biệt **Firebase Authentication + Firestore Security Rules** với **server Java SDK + IAM**.
7. Kiểm tra edition/mode/location của database qua CLI và tạo database lab có kiểm soát.
8. Sử dụng Java Firestore SDK với **named database**, hiểu khác biệt so với Datastore/MongoDB client.
9. Đánh giá migration, indexes, bảo mật, nhất quán, scale, backup và chi phí.
10. Hoàn thành bài tập kiến trúc và checklist production.

## 2. Hai trục chọn Firestore: Edition và Data Access Mode

~~~mermaid
flowchart TD
    Start["Cần Firestore database"]
    E{"Chọn edition"}
    S["Standard"]
    Ent["Enterprise"]
    N1["Native mode<br/>Firestore Core API"]
    D["Datastore mode<br/>Datastore API"]
    N2["Native mode<br/>Core + Pipeline API"]
    M["MongoDB compatibility<br/>MongoDB drivers/MQL"]
    Start --> E
    E --> S
    E --> Ent
    S --> N1
    S --> D
    Ent --> N2
    Ent --> M
~~~

| Edition | Data access mode được hỗ trợ | Ý nghĩa |
|---|---|---|
| **Standard** | **Native** | Firebase SDK/mobile/web, Firestore Core SDKs, query engine chuẩn |
| **Standard** | **Datastore** | Tương thích Datastore API, các ứng dụng cũ phụ thuộc Datastore |
| **Enterprise** | **Native** | Firestore Core **và Pipeline operations**, query engine nâng cao |
| **Enterprise** | **MongoDB compatibility** | Truy cập qua MongoDB-compatible APIs/drivers và BSON/MQL hỗ trợ |

**Mode không phải “mức giá” và edition không phải “kiểu API”.** Ví dụ hai database cùng là **Native mode** có thể dùng hai editions khác nhau, dẫn đến khác biệt về index, truy vấn và giá. Mỗi database chọn một data access mode; **không thể dùng cùng một database để vừa nhận Datastore API vừa cung cấp toàn bộ Firestore Native SDK**.

### 2.1. Firestore, Firebase và Cloud Datastore có phải ba cơ sở dữ liệu riêng?

- **Cloud Firestore** là dịch vụ database của Google Cloud, được dùng cả từ Google Cloud console lẫn hệ sinh thái Firebase.
- **Firebase** là nền tảng phát triển ứng dụng; Firebase Authentication và client SDK hỗ trợ kết nối tới Firestore Native mode.
- **Cloud Datastore** là API/hệ sinh thái trước đó. Firestore in Datastore mode cung cấp tầng **Datastore API compatibility**, chủ yếu cho những workload có phụ thuộc lịch sử.
- **Firestore with MongoDB compatibility** sử dụng API/driver tương thích MongoDB, **không tự động là MongoDB Atlas hoặc một MongoDB server có mọi tính năng tương đương**.

Tên trên UI/SDK và một số hướng dẫn cũ có thể dùng cách phân loại đơn giản hơn; khi thiết kế mới, hãy kiểm tra **edition + data access mode + database ID + location** thực tế.

### 2.2. Có thể có nhiều database trong một project không?

**Có**, Firestore hỗ trợ nhiều databases trong project, gồm editions/modes phù hợp với từng database. Chẳng hạn bạn có thể có một Native database cho ứng dụng Firebase và một Datastore-mode database phục vụ ứng dụng cũ, theo giới hạn sản phẩm hiện hành.

Nhưng cần lưu ý:

- Client SDK thường mặc định trỏ vào database **`(default)`**. Với **named database**, phải chỉ định ID rõ.
- **App Engine Datastore** có những ràng buộc với database `(default)` và edition/mode được hỗ trợ; không coi named database tùy ý là drop-in replacement.
- Security Rules, IAM, indexes, backup/PITR, metrics và location có thể cần quản lý **theo database**.
- **Free tier** không được nhân lên theo số databases: thường chỉ **một database trong project** hưởng free tier theo quy định hiện hành.

## 3. Firestore in Native mode: cho ứng dụng hiện đại

### 3.1. Mô hình collection/document

~~~text
orders                      (collection)
└── order-a71c               (document)
    ├── customerId: "u-42"
    ├── tenantId: "shop-a"
    ├── status: "CREATED"
    ├── amountMinor: 129900
    ├── createdAt: timestamp
    └── lines                 (subcollection)
        └── line-1            (document)
            ├── sku: "SKU-9"
            └── quantity: 2
~~~

Các khái niệm:

- **Collection:** tập các documents có tên.
- **Document:** tập field-value (string, number, boolean, timestamp, array, map, reference...).
- **Subcollection:** collection lồng dưới đường dẫn document; không có nghĩa xóa document cha sẽ tự xóa mọi dữ liệu của subcollection.
- **Document reference/path:** ID mang cấu trúc và được dùng để đọc/ghi/query.
- **Transaction/batched writes:** cho các thay đổi nhiều documents theo ràng buộc được hỗ trợ; không phải SQL transaction tùy ý với JOIN và foreign key.

**Native phù hợp** khi cần SDK cho web/iOS/Android, **realtime listeners**, offline caching/synchronization và data model được thiết kế theo các access patterns của ứng dụng. Java backend trên Cloud Run/GKE cũng có thể dùng **Firestore server client libraries** cùng mode này.

### 3.2. Realtime và offline

Firebase/Firestore mobile & web SDK có thể hỗ trợ:

- **Realtime listener** cập nhật document/query khi dữ liệu thay đổi.
- **Offline cache/persistence** theo SDK/platform và cấu hình hỗ trợ.
- Đồng bộ khi kết nối mạng trở lại với các quy tắc về offline writes và conflict behavior.

**Không nhầm:** realtime/offline của **Firestore Native Core operations** không có nghĩa mọi **Enterprise Pipeline query** đều được hỗ trợ realtime/offline. Với Enterprise Native, kiểm tra **cấu hình realtime updates** của database và phạm vi API được hỗ trợ.

### 3.3. Truy vấn Native khác SQL

~~~text
Lấy đơn của một người dùng:
collection("orders")
  .whereEqualTo("customerId", "u-42")
  .whereEqualTo("status", "CREATED")
  .orderBy("createdAt")
~~~

Điểm đáng lưu ý:

- Firestore Native Standard dựa vào **indexes** cho query; query phối hợp nhiều fields có thể cần **composite index**.
- Không có cơ chế SQL foreign keys hay join tùy ý ở **Standard Core queries**. Nên thiết kế theo read patterns, chấp nhận một phần duplication có kiểm soát.
- Transactions có semantics và giới hạn riêng; không mặc định mô hình lock của PostgreSQL.
- Document size của **Native mode** ở cả Standard và Enterprise được giới hạn **1 MiB** theo tài liệu hiện hành; không nhét file PDF/image lớn vào document. Dùng Cloud Storage chứa file, Firestore lưu metadata.

## 4. Firestore in Datastore mode: tương thích ứng dụng cũ

Datastore mode cung cấp API của Datastore cho hệ thống đã xây dựng theo **entities, kinds, keys, namespaces và ancestor queries**.

| Thành phần | Datastore API | Firestore Native API |
|---|---|---|
| Kiểu bản ghi | **Entity** | **Document** |
| Nhóm dữ liệu | **Kind** | **Collection** |
| Định danh | **Key** / key path | Document reference/path |
| Quan hệ cha-con | Ancestor/entity group | Document/subcollection hierarchy |
| SDK Java | `google-cloud-datastore` | `google-cloud-firestore` |
| Firebase mobile/web realtime | **Không** | **Có** qua Native Core khi cấu hình phù hợp |
| Firestore Security Rules cho Firebase SDK | **Không dùng theo cách Native** | **Có** đối với client mobile/web |
| Tình huống tốt nhất | Legacy App Engine/Datastore | Ứng dụng mới dùng Firestore API |

### 4.1. Vì sao vẫn chọn Datastore mode?

Nếu ứng dụng App Engine Java đang dùng Datastore `Entity`/`Key`/`Query`, chuyển ngay toàn bộ data model, indexes và code sang Native có thể tăng rủi ro mà không đem lại lợi ích cấp bách. Datastore compatibility giúp giữ ứng dụng hoạt động, chuyển đổi dần theo kế hoạch.

**Tài liệu Google Cloud khuyến nghị Datastore compatibility chủ yếu cho workload đang phụ thuộc Datastore APIs.** Với ứng dụng mới không bị ràng buộc legacy API, thường **không chọn Datastore mode** chỉ vì code chạy ở backend Java. Native mode cũng hỗ trợ server-side Java.

### 4.2. Datastore mode **không** mở khóa các tính năng Native

Một database Datastore-mode **không tự hỗ trợ**:

- Firebase Native mobile/web SDK và Firestore realtime/offline listeners.
- Full Firestore Native query surface.
- Hệ thống indexes và truy vấn của Native.
- Firebase Firestore Security Rules như với Native client SDK.

**Không giả định** rằng đổi import thư viện Java từ `Datastore` sang `Firestore` là dùng lại ngay cùng một database. Đây là ranh giới mode/API, không chỉ khác tên classes.

## 5. Firestore with MongoDB compatibility: Enterprise edition

Đây là **data access mode của Firestore Enterprise** dành cho ứng dụng muốn sử dụng **MongoDB driver, BSON types và MongoDB Query Language (MQL) trong tập tính năng được hỗ trợ**.

~~~mermaid
flowchart LR
    Java["Java service<br/>MongoDB driver"]
    Conn["TLS + OIDC / auth<br/>loadBalanced mode"]
    Mongo["Firestore Enterprise<br/>MongoDB compatibility"]
    Query["MQL/BSON<br/>supported subset"]
    Java --> Conn --> Mongo --> Query
~~~

### 5.1. Khi phù hợp

- Dự án có **MongoDB drivers/model/data access code** và muốn đánh giá Firestore managed infrastructure.
- Đội ngũ phụ thuộc một tập MQL/BSON và công cụ MongoDB đã được dịch vụ hỗ trợ.
- Cần query engine Enterprise và mô hình chi phí/scale đáp ứng khối lượng thực tế.

### 5.2. Những giả định nguy hiểm

- **Không phải 100% binary/feature compatibility** với mọi bản MongoDB/Atlas. Cần đối chiếu **supported MongoDB versions, commands, operators, drivers, index types và transaction limits** trước migration.
- Client phải dùng cấu hình được Google hỗ trợ, gồm **TLS**, **load-balanced mode** và **disable retryable writes** theo hướng dẫn kết nối hiện hành.
- **Java MongoDB driver 5.x** là một dòng được tài liệu hỗ trợ; OIDC authentication còn có minimum driver version riêng.
- Với MongoDB compatibility, giới hạn document có thể tới **16 MiB** (khác Native 1 MiB); hãy xác nhận trên tài liệu edition và workload cụ thể.
- **Không dùng Firebase Native realtime listener/Security Rules như cùng một API** trên database MongoDB compatibility.
- Một ứng dụng MongoDB có các aggregation/procedure/index đặc thù vẫn cần proof-of-concept; không quảng bá “chỉ thay URI là xong”.

### 5.3. Các bước kiểm chứng Java

~~~text
1. Tạo Enterprise database với MongoDB compatibility.
2. Lấy connection string bằng công cụ Google Cloud chính thức.
3. Chọn Java MongoDB driver được hỗ trợ; cấu hình TLS/auth.
4. Bật loadBalanced, tắt retryWrites theo tài liệu.
5. Chạy bộ kiểm thử CRUD, query, aggregation, transaction.
6. So sánh indexes, latency p95/p99 và hóa đơn.
7. Lập phương án rollback về database gốc trước cutover.
~~~

**Đừng tự chế connection string chỉ từ project ID và hostname.** Firestore MongoDB compatibility có **database UID** và yêu cầu kết nối riêng; lấy URI từ Google Cloud Console/CLI, giữ credential an toàn.

## 6. Standard vs Enterprise: cùng Native nhưng khác hành vi

| Tiêu chí | Standard + Native | Enterprise + Native |
|---|---|---|
| Query API | Firestore **Core operations** | Core **và Pipeline operations** |
| Engine | Standard query engine | Advanced query engine |
| Index single-field | Được tạo tự động theo mặc định | **Không tự tạo** |
| Query thiếu index | Thường bị từ chối và yêu cầu index phù hợp | **Có thể thực thi bằng scan**, nhưng có nguy cơ latency/cost cao |
| Composite / custom indexes | Cấu hình khi query cần | Tự quyết định và tối ưu với các loại index được hỗ trợ |
| Realtime/offline Core | Hỗ trợ bằng Firebase SDK | Hỗ trợ Core khi cấu hình capability phù hợp |
| Pipeline advanced queries | Không | Có |
| Document size Native | Tới **1 MiB** | Tới **1 MiB** |
| Charging focus | Document reads/writes/deletes, index entries, storage, egress | **Read/write units theo dung lượng byte**, storage, egress |
| Ưu tiên | Phần lớn ứng dụng Firebase/mobile & Java thông thường | Truy vấn nâng cao, yêu cầu hiệu năng và quản trị indexes chuyên sâu |

**Tính năng Enterprise không đồng nghĩa lúc nào cũng nhanh hoặc rẻ hơn.** Nếu ứng dụng query nhiều collection lớn mà không tạo indexes trên Enterprise, engine có thể phải scan rất nhiều documents, tăng latency/đơn vị đọc dù query vẫn chạy được.

### 6.1. Ví dụ query và chi phí

Một Java API truy vấn:

~~~text
orders where tenantId = "shop-a"
  and status = "PAID"
  order by createdAt desc
  limit 20
~~~

- **Standard:** cần index tương thích; nếu chưa có composite index, tạo index được hệ thống gợi ý rồi kiểm thử.
- **Enterprise Native:** query vẫn có thể chạy không index, nhưng scan nhiều dữ liệu khi volume lớn; dùng **Query Explain/Insights** và tạo index phù hợp.
- **Datastore mode:** phải viết lại query bằng Datastore API, tuân theo index/rules của Datastore.
- **Mongo compatibility:** viết bằng MQL/driver tương thích, kiểm tra supported operators và index plan.

Cùng một query logic nhưng **API, index và billing** có thể khác đáng kể. Khi benchmark, so sánh **chi phí trên một transaction đạt SLO** chứ không chỉ đơn giá read.

### 6.2. Nên chọn Enterprise khi nào?

Có thể cân nhắc nếu workload có một hoặc nhiều yêu cầu:

- Cần **Pipeline operations** nâng cao ngoài Core API.
- Có nhiều query động và muốn linh hoạt quản trị indexes theo workload.
- Đang cân nhắc MongoDB compatibility.
- Cần mục tiêu hiệu năng/tail latency đặc thù, đã đo trong môi trường đại diện.
- Đã kiểm tra mô hình billing Enterprise trên query bytes, storage và network.

**Không nâng toàn bộ databases lên Enterprise chỉ vì từ “Enterprise” nghe an toàn hơn.** Standard vẫn hỗ trợ nhiều biện pháp backup/PITR, IAM, encryption và high availability tùy cấu hình.

## 7. Ma trận chọn mode cho kiến trúc Java và Firebase

| Tình huống | Chọn đầu tiên | Lý do | Kiểm tra thêm |
|---|---|---|---|
| Chat realtime trên Android/iOS/web | **Standard + Native** | Firebase SDK, listeners và offline | Security Rules, index, read amplification |
| Java Orders API trên Cloud Run, CRUD/order status | **Standard + Native** | Java Firestore SDK, managed NoSQL, ít vận hành | Transaction patterns, composite indexes, tenant authorization |
| Java backend có query động rất phức tạp | **Enterprise + Native** | Advanced Core/Pipeline, index linh hoạt | Scans, supported Pipeline, billing |
| App Engine Java legacy dùng Datastore API | **Standard + Datastore** | Giữ code/entities/keys/indexes | Default DB constraints và migration plan |
| Java dịch vụ dùng MongoDB driver/MQL | **Enterprise + MongoDB compatibility** | Tái sử dụng driver/data model tương thích | Supported commands, TLS/OIDC, retryWrites |
| Java API cần nhiều JOIN, foreign keys, SQL transactions | **Cloud SQL/AlloyDB** trước khi chọn Firestore | Quan hệ và integrity requirements | TCO DB, SQL schema, concurrency |
| Event analytics/OLAP quét dữ liệu lớn | **BigQuery** trước khi chọn Firestore | Query analytics quy mô lớn | Ingestion, latency, cost |
| Chỉ cần lưu file/PDF/ảnh | **Cloud Storage** + Firestore metadata | Blob storage phù hợp hơn | Access control và object lifecycle |

**Chọn Firestore không vì “serverless nên không cần thiết kế”.** NoSQL giúp tránh vận hành server database, nhưng **data modeling, indexes, access rules, hotspots, backup, observability và billing** vẫn là trách nhiệm của nhóm.

## 8. Bảo mật: Firebase Security Rules không phải Google Cloud IAM

### 8.1. Hai loại client khác nhau

~~~mermaid
flowchart LR
    Mobile["Mobile/Web app"]
    Auth["Firebase Authentication"]
    Rules["Firestore Security Rules"]
    Native["Firestore Native database"]
    Java["Java API trên Cloud Run"]
    ADC["Runtime Service Account + IAM"]
    Mobile --> Auth --> Rules --> Native
    Java --> ADC --> Native
~~~

| Client | Cơ chế xác thực/phân quyền | Điều cần nhớ |
|---|---|---|
| Mobile/web dùng Firebase client SDK | Firebase Authentication + **Firestore Security Rules** | Rule kiểm tra access theo user/document |
| Server Java dùng Google Cloud Firestore client | **Application Default Credentials + IAM** | **Không thực thi Firestore Security Rules** |
| Firebase Admin SDK | Google credential + IAM | Quyền server; không đi qua Rules |
| Datastore-mode server client | Google Cloud IAM | Không dùng Firebase Rules như Native |
| MongoDB-compatible client | Authentication/authorization của mode tương ứng | Không mặc định dùng Firebase Rules |

**Sai lầm nghiêm trọng:** đặt Firestore Rules `allow read, write: if false` rồi nghĩ Java server không thể đọc database. **Server SDK bypass Security Rules** và dùng quyền IAM. Ngược lại, việc cấp `roles/datastore.user` cho Cloud Run runtime service account **không cấp quyền** cho Firebase mobile client bị Rules từ chối.

### 8.2. Ví dụ Rules cho ứng dụng đơn hàng

Mẫu Rules **chỉ đọc document thuộc người đăng nhập**, cho phép tạo order tối giản và không cho sửa/xóa trực tiếp từ client:

~~~javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /orders/{orderId} {
      allow read: if request.auth != null
                  && resource.data.ownerUid == request.auth.uid;

      allow create: if request.auth != null
                    && request.resource.data.ownerUid == request.auth.uid
                    && request.resource.data.status == 'CREATED'
                    && request.resource.data.keys().hasOnly(
                         ['ownerUid', 'status', 'createdAt']);

      allow update, delete: if false;
    }
  }
}
~~~

**Rules không phải bộ lọc kết quả của query.** Client query `orders` mà **không** giới hạn `ownerUid` có thể bị từ chối, ngay cả khi một phần documents thuộc user; hãy thiết kế query/rules tương thích và test bằng **Firebase Emulator Suite**. Mẫu chặn việc client tự tạo đơn `status=PAID`, nhưng **chưa đủ validation nghiệp vụ** (thời gian tạo, danh mục fields và chứng từ); giao dịch thanh toán nên được thực hiện qua Java backend có kiểm tra/transaction.

### 8.3. Java backend phải kiểm tra tenant

Nếu Cloud Run Java dùng runtime SA có quyền đọc collection `orders`, nó cần:

1. Xác minh JWT/session của HTTP caller.
2. Xác định `tenantId`/`uid` từ danh tính đã xác minh, **không tin header caller tự ghi**.
3. Query/đọc đúng document và kiểm tra quyền ở domain layer.
4. Ghi audit business access, hạn chế log PII/credential.
5. Dùng IAM least privilege cho workload SA, tránh `Owner/Editor`.

Firestore Rules **không bảo vệ khỏi lỗi authorization trong Java server** vì server IAM đã có quyền truy cập theo phạm vi được cấp.

## 9. Thực hành A — Kiểm tra edition/mode/location an toàn

**Lệnh đọc**, không tạo/xóa tài nguyên:

~~~bash
gcloud auth list
gcloud config get-value project

gcloud firestore databases list \
  --project=PROJECT_ID

gcloud firestore databases describe \
  --project=PROJECT_ID \
  --database="(default)"
~~~

Với named database, thay `(default)` bằng ID thật. Kiểm tra:

- **edition**: STANDARD/ENTERPRISE;
- **type / access mode**: FIRESTORE_NATIVE, DATASTORE_MODE hoặc các capability flags của Enterprise;
- **locationId**;
- **deleteProtectionState**;
- indexes, TTL, backup/PITR và các thiết lập khác khi được hỗ trợ.

**Đừng suy mode chỉ từ tên database**; một database có tên `orders-native` vẫn có thể khác mode nếu được tạo sai. Trước khi dùng SDK Java, kiểm tra ID, project và edition/mode qua resource thật.

### 9.1. Tạo Standard + Native cho lab

**Lệnh này tạo database và có thể phát sinh phí.** Chọn location được Firestore Standard hỗ trợ và theo data residency:

~~~bash
gcloud firestore databases create \
  --project=PROJECT_ID \
  --database=orders-native-lab \
  --location=asia-southeast1 \
  --edition=standard \
  --type=firestore-native \
  --delete-protection
~~~

`--delete-protection` là lớp chống xóa nhầm. Nếu muốn dọn sau lab, phải **tắt deletion protection có chủ đích** trước khi delete; không xóa database do nhóm khác sở hữu. Nếu ứng dụng dùng Firebase web/mobile, hãy cấu hình **Security Rules hạn chế** cho database vừa tạo trước khi đưa client truy cập.

### 9.2. Tạo Standard + Datastore cho app legacy

Chỉ minh họa **một lựa chọn khác**, không bắt buộc tạo cả hai database:

~~~bash
gcloud firestore databases create \
  --project=PROJECT_ID \
  --database=legacy-datastore-lab \
  --location=asia-southeast1 \
  --edition=standard \
  --type=datastore-mode \
  --delete-protection
~~~

Database này dùng **Datastore API**, **không** phải Native SDK. Với App Engine Datastore cũ, cần kiểm tra database `(default)` và project/App Engine location constraints; named database mới **không tự thay** datastore mặc định của ứng dụng.

### 9.3. Tạo Enterprise + Native khi cần query nâng cao

Theo hướng dẫn Firestore Enterprise hiện hành, cấu hình mẫu:

~~~bash
gcloud firestore databases create \
  --project=PROJECT_ID \
  --database=orders-enterprise-lab \
  --location=LOCATION_SUPPORTED_BY_ENTERPRISE \
  --edition=enterprise \
  --enable-firestore-data-access \
  --no-enable-mongodb-compatible-data-access \
  --enable-realtime-updates \
  --delete-protection
~~~

**Thay location bằng giá trị thực được edition hỗ trợ**. Trong trường hợp muốn MongoDB-compatible APIs, chọn **Enterprise + MongoDB compatibility** khi tạo database, **không** bật đồng thời hai API chỉ vì muốn dùng chung collections từ cả hai driver. Kiểm tra flags tạo database trong tài liệu CLI mới nhất.

**Location không đổi được sau khi tạo database.** Với database có dữ liệu, hãy lên kế hoạch migration khi muốn chuyển mode/edition, không dựa vào thao tác một click. Tài liệu quản lý cho phép sửa **Native/Datastore type của database rỗng** trong những điều kiện được hỗ trợ, nhưng đây không phải chiến lược chuyển hệ thống production có dữ liệu.

## 10. Thực hành B — Java 17 truy cập Firestore Native

Đây là **Java server SDK**, phù hợp chạy Cloud Run/GKE/Compute Engine, **không phải Firebase mobile client**. Nó sử dụng **ADC của runtime principal** và được kiểm soát bằng IAM.

### 10.1. Maven dependencies

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>firestore-mode-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>libraries-bom</artifactId>
        <version>26.90.0</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.google.cloud</groupId>
      <artifactId>google-cloud-firestore</artifactId>
    </dependency>
  </dependencies>
</project>
~~~

Phiên bản BOM là **ví dụ cần khóa và kiểm tra compatibility**, không phải khẳng định mới nhất; thay bằng version đã được thử trong CI, rà soát advisories trước nâng cấp.

### 10.2. Java tạo và truy vấn document

Đặt file `src/main/java/com/example/FirestoreOrdersDemo.java`:

~~~java
package com.example;

import com.google.cloud.firestore.DocumentReference;
import com.google.cloud.firestore.FieldValue;
import com.google.cloud.firestore.Firestore;
import com.google.cloud.firestore.FirestoreOptions;
import com.google.cloud.firestore.QueryDocumentSnapshot;
import java.util.List;
import java.util.Map;

public final class FirestoreOrdersDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: FirestoreOrdersDemo PROJECT_ID DATABASE_ID");
        }

        String projectId = args[0];
        String databaseId = args[1];

        try (Firestore db = FirestoreOptions.newBuilder()
                .setProjectId(projectId)
                .setDatabaseId(databaseId)
                .build()
                .getService()) {

            DocumentReference orderRef =
                db.collection("orders").document("order-lab-001");

            Map<String, Object> order = Map.of(
                "ownerUid", "demo-user",
                "tenantId", "shop-a",
                "status", "CREATED",
                "amountMinor", 129900L,
                "createdAt", FieldValue.serverTimestamp());

            // create() thất bại nếu document tồn tại; chỉ chạy 1 lần
            // hoặc dùng test ID khác trong sandbox.
            orderRef.create(order).get();

            List<QueryDocumentSnapshot> found = db.collection("orders")
                .whereEqualTo("tenantId", "shop-a")
                .whereEqualTo("status", "CREATED")
                .get()
                .getDocuments();

            for (QueryDocumentSnapshot doc : found) {
                System.out.println(doc.getId()
                    + " => " + doc.getString("status"));
            }
        }
    }
}
~~~

**Chú ý:**

- `setDatabaseId(...)` quan trọng khi sử dụng **named database**, vì mặc định SDK trỏ tới `(default)`.
- `create()` không ghi đè document hiện hữu; khi chạy lại có thể nhận `ALREADY_EXISTS`, đó là hành vi mong đợi của demo. Trên production, chọn idempotency key và write strategy phù hợp.
- Nếu thêm sort theo `createdAt` vào query kết hợp filters ở Standard, có thể cần **composite index**.
- `FieldValue.serverTimestamp()` là timestamp do Firestore server gán.
- **Java server client bypass Firestore Security Rules**, nên runtime service account phải có IAM phù hợp, ví dụ quyền data access thuộc `roles/datastore.user` khi cần. Nên dùng service account riêng, không cấp Owner/Editor.
- **Không đặt service account JSON key trong Maven repo**. Trên Cloud Run/GKE, dùng runtime identity; trên laptop, đăng nhập ADC bằng quy trình được tổ chức cho phép.

### 10.3. Nếu backend vẫn dùng Datastore API

Không chuyển sang `FirestoreOptions` trên Datastore-mode database. Một minh họa SDK khác:

~~~java
import com.google.cloud.datastore.Datastore;
import com.google.cloud.datastore.DatastoreOptions;
import com.google.cloud.datastore.Entity;
import com.google.cloud.datastore.Key;

// Dependency: com.google.cloud:google-cloud-datastore
Datastore datastore = DatastoreOptions.newBuilder()
    .setProjectId("PROJECT_ID")
    .build()
    .getService();

Key key = datastore.newKeyFactory()
    .setKind("Order")
    .newKey("order-lab-001");

Entity orderEntity = Entity.newBuilder(key)
    .set("status", "CREATED")
    .set("tenantId", "shop-a")
    .build();

datastore.put(orderEntity); // Tạo/sửa entity thật nếu chạy.
~~~

Đây là **đoạn Java minh họa**, không phải chương trình biên dịch độc lập. `DatastoreOptions`/`Entity`/`Key` phản ánh mô hình Datastore. Nếu project có nhiều databases, phải cấu hình database target theo khả năng SDK và project architecture thực tế; đừng mặc định Datastore client luôn chọn đúng named database.

## 11. Index, scale, consistency và mô hình dữ liệu

### 11.1. Không truy vấn tùy ý mà không đo cost

| Vấn đề | Standard Native | Enterprise Native |
|---|---|---|
| Query phức hợp thiếu index | Có thể báo thiếu index | Có thể chạy bằng scan rất tốn kém |
| Index trên trường ít sử dụng | Thường có automatic single-field | Không tự tạo, giảm write/index overhead nếu kiểm soát tốt |
| Query thường xuyên | Tạo composite index khi được yêu cầu | Tạo index chủ đích theo explain/insights |
| Thay query code | Có thể cần deploy index trước | Có thể chạy ngay nhưng performance/cost biến đổi |

Bài toán Orders API: query theo `tenantId` và `status` sẽ tăng theo số documents. Nếu 100.000 orders mà chỉ 50 orders cần hiển thị, cần **index/query plan** phù hợp. Không kéo toàn bộ collection về Java để filter; hành động đó tăng reads và có thể lộ dữ liệu ngoài tenant.

### 11.2. Tránh hotspot

- **Không** dùng document IDs tăng dần như `order-000001`, `order-000002` ở tốc độ ghi cao; ưu tiên auto-ID/random ID hoặc key phân tán có kiểm soát.
- Tránh tập trung lượng lớn writes vào **một document counter**; cân nhắc distributed counters/aggregation.
- Với timestamp tăng dần được index và ghi tốc độ cao, xem best practices **index exemption, ramp-up traffic và 500/50/5 guidance** theo edition/khối lượng; không gán một throughput cố định cho mọi database.
- Không biến một document thành danh sách tất cả order lines vô hạn; giới hạn 1 MiB Native và write contention.
- Data modeling nên xuất phát từ **query patterns**, không sao chép nguyên ERD nhiều JOIN của PostgreSQL.

### 11.3. Consistency và transactions

Firestore có **strongly consistent queries** và hỗ trợ transactions/batched writes theo API. Nhưng:

- Transaction có retry, size/time limits và collision behavior riêng.
- Không mặc định cơ chế relational constraints hay foreign keys.
- Offline client writes và listener UI có thể hiển thị trạng thái local trước khi server xác nhận; ứng dụng phải xử lý pending writes/conflict.
- Dữ liệu tài chính/kiểm soát tồn kho cần thiết kế idempotency và invariants, không chỉ dựa vào việc dùng database NoSQL.

Nếu một nghiệp vụ cần cross-table joins mạnh, nhiều transactions dài và các constraints SQL, **Cloud SQL/AlloyDB** có thể là lựa chọn hợp lý hơn Firestore.

## 12. Migration giữa modes/editions: dự án riêng, không đổi flag tùy tiện

### 12.1. Khi nào migration cần thiết?

- App Engine Datastore legacy chuẩn bị triển khai realtime mobile.
- Standard Native workload cần Enterprise Core/Pipeline.
- MongoDB application muốn thử Firestore with MongoDB compatibility.
- Cần thay location hoặc tách data residency sang project khác.

**Không giả định** mọi trường hợp chỉ cần đổi `--edition` hoặc `--type` trên database có dữ liệu. Lựa chọn an toàn là **tạo database đích**, dịch chuyển dữ liệu/cấu hình, kiểm chứng và cutover có rollback. Với Standard Native → Enterprise Native, tài liệu hướng dẫn **Firestore import/export hoặc Dataflow Firestore-to-Firestore**.

### 12.2. Runbook di chuyển

~~~mermaid
flowchart TD
    Plan["Inventory APIs, data model,<br/>index, rules, IAM, costs"]
    New["Tạo database đích<br/>edition/mode/location"]
    Copy["Export/import hoặc<br/>pipeline chuyển đổi"]
    Validate["So dữ liệu, query,<br/>transactions và performance"]
    Cut["Cutover client traffic<br/>và quan sát"]
    Rollback["Rollback plan và<br/>ngừng dual-write đúng quy trình"]
    Plan --> New --> Copy --> Validate --> Cut --> Rollback
~~~

1. **Kiểm kê** SDK/API, schema, documents/entities, indexes, security rules, IAM, TTL, backups/PITR, triggers và integration.
2. **Chọn edition/mode/region** của database đích; kiểm tra constraints của database `(default)` và App Engine.
3. **Chuyển data** bằng export/import hoặc Dataflow nếu có workflow phù hợp; với Datastore → Native hoặc Mongo compatibility phải đối chiếu **data model và API differences** riêng.
4. **Dựng lại cấu hình**: indexes, Rules, IAM, TTL, backups, PITR, CMEK, metrics/triggers. Dataflow migration **không tự chuyển tất cả cấu hình**.
5. **Kiểm chứng chức năng**: số lượng documents, references, timestamps, nulls, queries, transactions, security tests, p95/p99 và billing.
6. **Quản lý writes trong lúc copy**: chọn maintenance window, CDC/dual-write có idempotency nếu cần; một lần export không bảo đảm snapshot nhất quán với mọi write đang diễn ra.
7. **Cutover** SDK sang đúng database ID; theo dõi errors/lag/cost; giữ rollback rõ ràng, không xóa source ngay.
8. **Dọn dẹp** khi đã xác minh production ổn định và retention/compliance được phê duyệt.

**Một chi tiết dễ bỏ sót:** Firebase/client SDK có thể **mặc định trỏ `(default)`**. Sau migration sang database đặt tên, phải cập nhật client configuration và security rules cho **database đích**, nếu không app có thể tiếp tục đọc/ghi DB cũ.

## 13. Location, billing và vận hành

### 13.1. Location là quyết định khó đổi

Firestore hỗ trợ **regional** và **multi-region** locations trong các edition/location được công bố. Chọn theo:

- **Data residency** và yêu cầu pháp lý.
- **Độ trễ** giữa ứng dụng và database, nhất là Cloud Run/GKE region.
- **Availability/durability** và khả năng chịu lỗi vùng.
- **Chi phí operation/storage/network egress** theo location.
- Khả năng phối hợp với các dịch vụ khác, ví dụ Cloud Functions/Eventarc/BigQuery exports.

**Một khi database được tạo, location không đổi trực tiếp.** Với database `(default)`, location có thể bị ràng buộc bởi **default Google Cloud resources location** của project/Firebase/App Engine thiết lập trước đó. Đừng chọn theo mặc định của console mà không kiểm tra yêu cầu.

### 13.2. So sánh cách tính phí ở mức khái niệm

| Yếu tố | Standard | Enterprise |
|---|---|---|
| Data operation | Thường đếm document reads/writes/deletes và index-entry reads trong các trường hợp liên quan | Tính đơn vị đọc/ghi theo **lượng bytes được xử lý** |
| Indexing | Automatic index storage/write overhead | Index là lựa chọn chủ động, scan có thể tốn nhiều reads |
| Storage | Có phí theo dung lượng/snapshot theo cấu hình | Có phí theo dung lượng và các sản phẩm liên quan |
| Network egress | Có thể phát sinh | Có thể phát sinh |
| Realtime listeners | Có thể làm tăng số reads theo thay đổi dữ liệu | Core operations cũng cần đo reads/bytes và config |
| Free tier | Theo giới hạn và database đủ điều kiện | Theo giới hạn và database đủ điều kiện |

Ví dụ giả định app mở một trang danh sách 20 orders mỗi lần, mỗi user refresh 50 lần/ngày; 10.000 users/ngày tạo lượng reads đáng kể, ngay cả khi kích thước document nhỏ. Với Enterprise, **query thiếu index và scan nhiều dữ liệu** có thể làm hóa đơn khác hẳn Standard. Dùng **Cloud Billing Reports, Pricing Calculator, Query Explain/Insights** và sample traffic, không suy giá từ tên edition.

### 13.3. Vận hành cơ bản

- Dùng **IAM least privilege** cho Java server, Firebase Security Rules cho mobile/web.
- Chọn **delete protection**, backup, PITR và retention theo RPO/RTO nếu có nhu cầu.
- Theo dõi **latency, error rate, reads/writes, index/storage, query scans và quota**.
- Xác minh **Firestore index/Rules deployment** trong CI/CD trước deploy code.
- Bảo vệ Cloud Functions/Eventarc triggers trước việc retry gây side effects trùng.
- Phân biệt Firestore document reads với dữ liệu tĩnh/file trong Cloud Storage.
- Kiểm tra khả năng phục hồi và hóa đơn của **named databases** riêng.

## 14. Chẩn đoán thường gặp

| Triệu chứng | Nguyên nhân có thể | Bước kiểm tra |
|---|---|---|
| Java SDK trả `NOT_FOUND` cho document trong UI | Java đang trỏ `(default)` thay vì named database | `setDatabaseId`, project ID và path |
| Mobile SDK `PERMISSION_DENIED` | Firestore Security Rules / Firebase Auth không khớp | Rules, token user, query constraints |
| Java SDK truy cập được dù Rules deny-all | Server SDK dùng **IAM**, bypass Rules | Runtime service account/IAM policy |
| Java server nhận `PERMISSION_DENIED` | Thiếu IAM Firestore data permissions | Principal ADC và `roles/datastore.user` hoặc custom role |
| Standard Native query yêu cầu index | Composite index thiếu | Tạo index theo gợi ý và chờ build |
| Enterprise query chạy nhưng chậm | Query scan nhiều documents vì không có index | Query Explain/Insights, tạo index |
| Datastore SDK không có realtime listener | Datastore mode không hỗ trợ Firebase Native API | Giữ Datastore hoặc thiết kế migration |
| Mongo driver không kết nối được | TLS/loadBalanced/retryWrites/OIDC driver chưa đúng | Official URI, driver support/config |
| App có hai clients cùng project nhưng khác kết quả | Dùng khác database ID/mode | Project + database ID + SDK type |
| Dữ liệu mới có hotspot | Sequential IDs/single document hoặc index timestamp | Document ID, workload writes, index exemptions |
| Data migration thiếu indexes | Export/import/Dataflow không mang đủ config | Tạo indexes/Rules/TTL/backup settings ở target |
| Billing tăng sau Enterprise switch | Scan, byte-based units, storage hoặc traffic | Query Explain và Billing Reports |
| DB tạo sai region | Location immutable sau khi tạo | Tạo DB khác, migration và cutover |
| Firebase console hiển thị Rules nhưng Java vẫn full access | Nhầm trust boundary | Test Rules client, kiểm soát IAM server |

### 14.1. Runbook ba bước để xác định lỗi thuộc lớp nào

1. **Đúng DB chưa?** Kiểm tra project ID, database ID, edition/mode, location, Java client target.
2. **Đúng danh tính chưa?** Với Firebase mobile/web: token + Rules; với Java server: ADC/IAM; với Mongo: authentication mechanism + supported driver.
3. **Đúng query/index chưa?** Kiểm tra field/collection, index cần thiết, query plan, dữ liệu tenant và quota. Sau đó mới điều chỉnh SDK/retry/capacity.

Không “sửa” `PERMISSION_DENIED` bằng cách mở Rules `allow read, write: if true` hoặc cấp project Owner.

## 15. Case study: ứng dụng bán lẻ đa kênh

**Bối cảnh giả định:** công ty RetailOne có:

- Mobile app hiển thị trạng thái đơn hàng realtime và cache khi mất mạng.
- **Java Orders API** trên Cloud Run quản lý đơn hàng/authorization.
- Một App Engine service cũ dùng Datastore entity `Customer`.
- Một nhóm khác đang thử Java MongoDB driver cho hệ thống gợi ý sản phẩm.
- Hàng triệu documents, traffic flash sale và yêu cầu quản lý chi phí.

### 15.1. Quyết định theo workload

| Workload | Edition/mode đề xuất | Vì sao |
|---|---|---|
| Mobile order tracking | **Standard + Native** | Realtime/offline Firebase SDK |
| Java Orders API | **Standard + Native** (cùng DB mobile nếu dùng chung data contract) | Java server SDK + IAM, kiểm soát nghiệp vụ |
| Legacy App Engine Datastore | **Standard + Datastore** ở phạm vi phù hợp | Giữ Datastore API cho tới khi migration sẵn sàng |
| Java Mongo-compatible recommendation service | **Enterprise + MongoDB compatibility** để POC | Kiểm tra MQL/driver compatibility và byte-based billing |
| Analytics/reporting lịch sử | **BigQuery** qua pipeline phù hợp | Không dùng Firestore làm kho OLAP chính |

**Không gộp tất cả dữ liệu vào một database chỉ để dùng một SDK.** Cùng Google Cloud project có thể có nhiều databases, nhưng phải quản lý default/named DB và network/iam/rules rõ ràng; một số workload nên dùng DB khác hoàn toàn theo yêu cầu.

### 15.2. Thiết kế bảo vệ dữ liệu đơn hàng

~~~mermaid
flowchart LR
    User["Firebase mobile user"]
    Auth["Firebase Auth + Rules"]
    F["Firestore Native orders"]
    Java["Cloud Run Java Orders API"]
    IAM["Java runtime SA + IAM"]
    Legacy["Legacy App Engine"]
    DS["Firestore Datastore mode"]
    User --> Auth --> F
    Java --> IAM --> F
    Legacy --> DS
~~~

- Mobile chỉ đọc orders của `ownerUid` đã xác minh, không được tự sửa `status=PAID`.
- Java Orders API xác minh user JWT/tenant, xử lý transaction logic rồi cập nhật Firestore.
- Java runtime dùng **user-managed service account** với IAM tối thiểu; Rules **không** giới hạn server SDK.
- Legacy App Engine tách dữ liệu Datastore đến khi chuyển migration có kiểm thử.
- MongoDB workload cần đo support/query cost, **không thay API gốc trong một ngày**.

### 15.3. Kế hoạch kiểm chứng

1. Đo **p95 latency**, query reads, index scans và write throughput trên traffic đại diện.
2. Đo listeners theo số người dùng đồng thời và hiệu ứng reconnect.
3. Chạy Rule tests bằng Firebase Emulator: user A không đọc được order user B.
4. Kiểm tra Java IAM: đúng service account; không cho service đọc ngoài yêu cầu.
5. Benchmark Standard Native với Enterprise Native nếu có query thực sự cần nâng cấp.
6. POC MongoDB driver với bộ test CRUD/MQL/transactions và thực đo billing.
7. Kiểm tra backups/PITR, location, index và chi phí chuyển dữ liệu.
8. Chọn phương án cutover/rollback theo data contract, không dựa vào nhãn sản phẩm.

## 16. Bài tập và tự đánh giá

### Bài 1 — Hai trục mode và edition

Một kỹ sư nói “Firestore Enterprise chính là MongoDB mode; Native chỉ có Standard”.

**Hỏi:** phát biểu sai ở đâu? Nêu đủ bốn tổ hợp edition/mode chính được hỗ trợ.

**Gợi ý:** Enterprise còn có Native Core/Pipeline; Standard có Native và Datastore.

### Bài 2 — Ứng dụng chat realtime

App mobile/web cần nhận message realtime và dùng offline cache; Java server kiểm duyệt nội dung.

**Hỏi:** chọn mode/edition nào trước? Hai nhóm client dùng cơ chế authorization nào?

**Gợi ý:** Native; Firebase Authentication/Rules cho app, IAM/domain validation cho Java server.

### Bài 3 — Legacy App Engine

Một App Engine Java service đã sử dụng `Datastore`/`Entity` trong nhiều năm. Nhóm muốn dùng Firebase listener bằng cách import Firestore SDK.

**Hỏi:** có thể giữ nguyên Datastore-mode database rồi chỉ thay SDK không?

**Gợi ý:** không; phải đánh giá migration database model/API, không chỉ dependency.

### Bài 4 — Enterprise thiếu index

Standard Native query thiếu composite index và báo lỗi. Sau khi đưa cùng query sang Enterprise Native, query chạy được nhưng p99 tăng gấp nhiều lần.

**Hỏi:** vì sao? Cần xem gì để sửa?

**Gợi ý:** Enterprise có thể chạy scan vì index optional; dùng Query Explain và index chủ đích.

### Bài 5 — Java access vs Rules

Rules đặt `allow read: if false`, nhưng Java server vẫn đọc được toàn bộ dữ liệu.

**Hỏi:** đây có phải lỗi Rules không? Cần kiểm soát lớp nào?

**Gợi ý:** server Java SDK bypass Rules, dùng runtime IAM và app authorization.

### Bài 6 — Named database

Project có `(default)` và `orders-native-lab`. Code Java dùng `FirestoreOptions.getDefaultInstance().getService()` và không thấy orders vừa viết.

**Hỏi:** cần thiết lập option nào? Cách xác minh resource thật?

**Gợi ý:** `setDatabaseId("orders-native-lab")` và đúng project, dùng `gcloud firestore databases describe`.

### Bài 7 — MongoDB-compatible Java

App dùng MongoDB Java driver 5.x và nhiều aggregations. Nhóm muốn chuyển sang Firestore Enterprise MongoDB compatibility.

**Hỏi:** cần kiểm chứng gì trước khi chuyển production?

**Gợi ý:** supported MQL/operators, driver/OIDC, TLS/load-balanced, retryable writes, indexes, latency/cost và rollback.

### Bài 8 — Chọn database cho quan hệ phức tạp

Hệ thống kế toán có nhiều bảng liên quan, transactions dài, foreign keys và các JOIN.

**Hỏi:** tại sao không nên mặc định chọn Firestore? Ứng viên GCP nào phù hợp hơn?

**Gợi ý:** Cloud SQL hoặc AlloyDB cho workload relational/transactional phù hợp.

### Bài 9 — Location và chi phí

Nhóm tạo database tại region xa người dùng, lưu dữ liệu lớn và nhiều queries scan. Sau đó muốn “đổi region” bằng một setting.

**Hỏi:** có đổi trực tiếp được không? Cần làm gì và đo những chi phí nào?

**Gợi ý:** location immutable; tạo target DB, migration, verify và cutover; theo dõi read/write units, egress, storage, index.

### Bài 10 — Thiết kế tích hợp

Hãy xây ma trận quyết định cho Java Orders API, Firebase mobile app và legacy Datastore app. Với mỗi workload nêu:

- Edition/mode và API/SDK;
- Document/entity data model, index/query access patterns;
- Firebase Security Rules hoặc IAM;
- Region, realtime/offline, consistency;
- Chi phí, scaling, backups và migration strategy.

**Gợi ý:** không ép legacy Datastore dùng Native SDK và không dùng Firebase Rules để bảo vệ Java server.

## 17. Checklist production

- [ ] Đã xác định **edition** và **data access mode** riêng, không nhầm Enterprise là Mongo-only.
- [ ] Chọn Native cho ứng dụng mới cần Firebase mobile/web SDK; Datastore chỉ khi có phụ thuộc API legacy.
- [ ] Với Mongo compatibility, có bộ test supported commands, drivers, auth, TLS, index và retry semantics.
- [ ] Đã xác minh database ID, `(default)` vs named database, project và location.
- [ ] Đã chọn region/multi-region theo latency, data residency, availability và chi phí.
- [ ] Có Firestore Security Rules cho mobile/web; kiểm thử bằng emulator.
- [ ] Java server dùng runtime service account + IAM, **không dựa vào Security Rules**.
- [ ] Không hardcode service account keys hoặc client secrets trong Java repo.
- [ ] Data model theo query patterns; không copy SQL JOIN/foreign keys sang Standard Native.
- [ ] Document IDs và write patterns tránh hotspots/single-document contention.
- [ ] Standard Native query có index đầy đủ; Enterprise query kiểm tra scans và tạo indexes chủ đích.
- [ ] Đã đo p95/p99, throughput, reads/writes, storage, egress và billing cho traffic thật.
- [ ] Đã đánh giá khác biệt pricing Standard document operations và Enterprise byte-based units.
- [ ] Realtime/offline chỉ kỳ vọng ở đúng SDK/Core mode và feature configuration.
- [ ] Có delete protection, backups/PITR/TTL phù hợp RPO/RTO và ngân sách.
- [ ] Migration có data validation, indexes/Rules/IAM transfer, cutover và rollback.
- [ ] CI/CD kiểm tra Security Rules, indexes, query changes và database IDs.
- [ ] Có monitoring/alert cho errors, latency, quota/index/storage và IAM changes.
- [ ] Không xóa nguồn dữ liệu hoặc đổi type của database đang có dữ liệu để thử tính năng.

## 18. Tài liệu Google Cloud và Firebase chính thức

Kiểm tra tài liệu hiện hành về editions/modes, SDK, pricing và limits trước khi dùng trong production:

- [Firestore — Editions overview](https://docs.cloud.google.com/firestore/native/docs/editions-overview)
- [Firebase — Firestore editions overview](https://firebase.google.com/docs/firestore/editions)
- [Firebase — Enterprise edition modes](https://firebase.google.com/docs/firestore/enterprise/overview-enterprise-edition-modes)
- [Firestore — Choose between Firestore APIs](https://docs.cloud.google.com/datastore/docs/firestore-or-datastore)
- [Firestore — Create and manage databases](https://docs.cloud.google.com/firestore/native/docs/manage-databases)
- [Firestore — Native vs Enterprise indexing](https://docs.cloud.google.com/firestore/native/docs/enterprise-index-overview)
- [Firestore — MongoDB compatibility](https://docs.cloud.google.com/firestore/mongodb-compatibility/docs)
- [Firestore — MongoDB connection requirements](https://docs.cloud.google.com/firestore/mongodb-compatibility/docs/connect)
- [Firestore — Supported MongoDB drivers](https://docs.cloud.google.com/firestore/mongodb-compatibility/docs/supported-data-types-drivers)
- [Firebase — Firestore Security Rules](https://firebase.google.com/docs/firestore/security/get-started)
- [Firebase — Test Security Rules with Emulator](https://firebase.google.com/docs/firestore/security/test-rules-emulator)
- [Firebase — SDKs and client libraries](https://firebase.google.com/docs/firestore/client/libraries)
- [Firestore — Location selection](https://docs.cloud.google.com/firestore/native/docs/locations)
- [Firestore — Best practices](https://docs.cloud.google.com/firestore/native/docs/best-practices)
- [Firestore — Migrate Standard to Enterprise](https://docs.cloud.google.com/firestore/native/docs/migrate-standard-to-enterprise)
- [Firestore — Export/import data](https://docs.cloud.google.com/firestore/native/docs/manage-data/export-import)
- [Firestore Java — FirestoreOptions.Builder](https://docs.cloud.google.com/java/docs/reference/google-cloud-firestore/latest/com.google.cloud.firestore.FirestoreOptions.Builder)

**Điểm cần nhớ:** **Mode quyết định API/SDK và cách ứng dụng truy cập dữ liệu; edition quyết định thêm query engine, indexing và mô hình tính phí.** Với hệ thống mới cần Firebase realtime/offline, thường bắt đầu ở **Standard + Native**. Giữ **Datastore mode** cho API legacy; thử **Enterprise + Native** khi cần truy vấn nâng cao và **Enterprise + MongoDB compatibility** khi có phụ thuộc MongoDB driver. Dù chọn tổ hợp nào, hãy kiểm chứng **database ID, quyền Firebase Rules vs IAM, query/index costs, location và kế hoạch migration** trước khi phát hành.
