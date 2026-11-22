# Thực hành backend Java dùng Firestore và Firebase Admin SDK

Ứng dụng Orders có giao diện web/mobile cho khách hàng xem đơn và đặt hàng. Firebase Authentication xác thực người dùng, **Spring Boot backend Java** kiểm tra ID token, còn **Cloud Firestore** lưu đơn hàng và tồn kho. Cách làm này giữ nghiệp vụ nhạy cảm ở server, tận dụng cơ sở dữ liệu document được quản lý và triển khai trên Cloud Run hoặc GKE mà không cần tự vận hành máy chủ database.

Bài thuộc chương **Firestore và Firebase** của module `CLOUD_PROVIDERS_GCP`, gắn với kiến thức project, IAM/VPC, Cloud Run, GKE, bảo mật dữ liệu, triển khai và giám sát chi phí. Chúng ta sẽ xây API nhỏ có **xác thực, đọc đơn theo chủ sở hữu, transaction đặt hàng có chống trùng** và kiểm thử qua Firebase Emulator Suite.

> Mọi project, UID, URL và đơn hàng dưới đây chỉ là dữ liệu thử. Firebase Admin SDK có đặc quyền **server-side**, không được nhúng vào web/mobile app hoặc gửi service account keys cho client. Những lệnh tạo tài nguyên, triển khai và ghi Firestore có thể phát sinh phí; chỉ chạy trong sandbox được ủy quyền.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt Firebase client SDK, Firebase Admin SDK và Google Cloud Firestore server client.
2. Khởi tạo Admin SDK bằng **Application Default Credentials (ADC)**, dùng `FirestoreClient` và `FirebaseAuth` dưới một Firebase project.
3. Xác minh **Firebase Authentication ID token** ở backend và thực thi phân quyền theo `uid`.
4. Viết Java API đọc và tạo document, dùng transaction cập nhật tồn kho nguyên tử, xử lý retry/idempotency.
5. Lọc/phân trang dữ liệu, hiểu composite indexes và nguyên tắc thiết kế document.
6. Kiểm thử bằng **Firestore/Auth emulators**, phân biệt thử Security Rules của client và IAM của server.
7. Triển khai lên Cloud Run với service account tối thiểu, quan sát lỗi/latency và kiểm soát chi phí.

## 2. Kiến trúc và ranh giới tin cậy

```mermaid
flowchart LR
  WEB["Web / Mobile client"] -->|"Sign in"| AUTH["Firebase Authentication"]
  AUTH -->|"Firebase ID token"| WEB
  WEB -->|"HTTPS + Bearer Firebase ID token"| API["Spring Boot API<br/>Cloud Run / GKE"]
  API -->|"FirebaseAuth.verifyIdToken"| AUTH
  API -->|"Admin SDK / Firestore server API<br/>IAM service account"| DB["Cloud Firestore<br/>orders, inventory"]
  WEB -.->|"Optional direct client SDK<br/>Security Rules"| DB
  API --> OBS["Cloud Logging / Monitoring"]
```

| Thành phần | Dùng SDK/credential nào? | Phạm vi kiểm soát |
| --- | --- | --- |
| Web/mobile | Firebase Authentication client SDK; Firestore client SDK nếu có truy cập trực tiếp | ID token người dùng, **Firestore Security Rules** cho truy cập trực tiếp |
| Java backend | Firebase Admin Java SDK + Firestore server client, ADC/Workload Identity | **Google Cloud IAM** cho danh tính server, authorization do backend viết |
| Firebase Auth | Phát và xác thực định danh người dùng | Token là **bằng chứng danh tính**, không tự quyết định quyền đọc mọi document |
| Firestore | Database document/collections | Atomic transactions, indexes, TTL và lưu trữ |
| Cloud Run/GKE | Service/workload identity và network | Không đặt key JSON tĩnh vào container |

**Quy tắc trọng tâm:** Firestore **server client libraries và Firebase Admin SDK bỏ qua Firestore Security Rules** và được kiểm soát bằng **IAM**. Vì thế Security Rules kiểu `request.auth.uid == resource.data.ownerUid` không bảo vệ một endpoint Java dùng Admin SDK. Backend phải tự kiểm tra token, chủ sở hữu, vai trò, tenant và trường dữ liệu cho từng thao tác. <https://firebase.google.com/docs/firestore/security/test-rules-emulator>

### 2.1. Phân biệt ba loại token

| Token | Ai cấp | Mục đích |
| --- | --- | --- |
| **Firebase ID token** | Firebase Authentication sau khi client đăng nhập | Client gửi trong `Authorization: Bearer ...`; Java xác minh bằng `FirebaseAuth.verifyIdToken` |
| **Firebase custom token** | Admin SDK của server | Client dùng để **đăng nhập với Firebase Auth**, không dùng trực tiếp như Bearer ID token của API |
| **Google-signed ID token cho Cloud Run IAM** | Google identity/Service Account | Bảo vệ Cloud Run bằng `roles/run.invoker`; **khác Firebase ID token** |

Nếu backend phục vụ người dùng web/mobile qua URL công khai của Cloud Run, thường cho phép request tới **lớp HTTP ingress** theo chính sách rồi bắt buộc **Firebase ID token + authorization nghiệp vụ trong ứng dụng**; điều này không tương đương “API không có bảo mật”. Nếu Cloud Run đặt ở chế độ IAM-private, client phải có **Google-signed ID token** cho lớp Cloud Run, điều mà Firebase ID token riêng lẻ không thỏa mãn. Chọn đúng kiến trúc ingress, API Gateway/LB/WAF và App Check tùy threat model.

## 3. Chuẩn bị Firebase project và Firestore

Ví dụ sử dụng:

| Thành phần | Giá trị minh họa |
| --- | --- |
| Google Cloud/Firebase project ID | `orders-lab` |
| Firestore database | `(default)`, **Native mode / Standard edition** |
| Region | Vùng gần ứng dụng, chọn lúc tạo database |
| Firebase Auth sign-in | Email/password trong **sandbox** |
| Backend | Java 21, Spring Boot 3.5.x, Firebase Admin Java 9.12.0 |
| Collections | `inventory/{sku}` và `orders/{orderId}` |

**Trước khi viết mã:**

1. Tạo/chọn **cùng một Google Cloud project** và thêm Firebase vào project nếu chưa có.
2. Bật Firebase Authentication và một nhà cung cấp đăng nhập (ví dụ Email/Password) trong Firebase console; chỉ tạo tài khoản thử.
3. Tạo Cloud Firestore **Native mode** database trong region thích hợp. Region/multi-region, edition và database ID ảnh hưởng API, latency và giá; không đổi tùy tiện sau khi ứng dụng có dữ liệu.
4. Trong Google Cloud, bật các APIs cần thiết và tạo **runtime service account** có quyền đọc/ghi Firestore ở phạm vi thích hợp.
5. Cài JDK 21, Maven hoặc Maven Wrapper, gcloud CLI và Firebase CLI cho emulator. Không cần Firebase client configuration API key ở server Java Admin SDK.

Lệnh kiểm tra chỉ đọc:

```bash
PROJECT_ID="orders-lab"
gcloud config get-value project
gcloud firestore databases list --project="$PROJECT_ID"
gcloud services list --enabled --project="$PROJECT_ID" \
  --filter="config.name:firestore.googleapis.com"
```

Với Cloud Run, **ADC nhận danh tính của runtime service account tự động**, không cần export `GOOGLE_APPLICATION_CREDENTIALS`. Ở máy phát triển, có thể dùng `gcloud auth application-default login` khi gọi Firestore sandbox hoặc dùng Emulator Suite; với Firebase Auth Admin SDK, user ADC có điều kiện riêng và có thể cần OAuth client ID phù hợp. Không tải một private key service account về máy chỉ để “làm cho chạy”.

## 4. Maven project và khởi tạo Firebase Admin SDK

Ví dụ cấu trúc ứng dụng:

```text
orders-backend/
  pom.xml
  src/main/java/com/example/orders/
    OrdersApplication.java
    FirebaseConfiguration.java
    OrdersController.java
  src/main/resources/application.properties
  Dockerfile                       # tùy chọn khi deploy Cloud Run
```

### 4.1. Cấu hình dependencies

File `pom.xml` tối thiểu:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>orders-backend</artifactId>
  <version>1.0.0</version>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>
  <properties>
    <java.version>21</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>com.google.firebase</groupId>
      <artifactId>firebase-admin</artifactId>
      <version>9.12.0</version>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
```

Tại ngày biên soạn, Firebase Admin Java **9.12.0 (11/2026)** có hỗ trợ xác minh App Check trên Java; đây là phiên bản minh họa đã được xác minh từ [release notes](https://firebase.google.com/support/release-notes/admin/java). Khi đưa production, cập nhật bản vá và quét dependencies, tránh kết hợp BOM/dependency overrides không tương thích. Firebase Admin SDK đã dùng các Firestore Java classes `com.google.cloud.firestore.*`; không cần tự thêm dependency Firestore lần hai cho mẫu cơ bản.

### 4.2. FirebaseConfiguration.java

```java
package com.example.orders;

import com.google.auth.oauth2.GoogleCredentials;
import com.google.cloud.firestore.Firestore;
import com.google.firebase.FirebaseApp;
import com.google.firebase.FirebaseOptions;
import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.cloud.FirestoreClient;
import java.io.IOException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class FirebaseConfiguration {
  @Bean(destroyMethod = "delete")
  FirebaseApp firebaseApp(@Value("${app.firebase.project-id}") String projectId)
      throws IOException {
    FirebaseOptions options = FirebaseOptions.builder()
        .setCredentials(GoogleCredentials.getApplicationDefault())
        .setProjectId(projectId)
        .build();
    return FirebaseApp.initializeApp(options);
  }

  @Bean
  FirebaseAuth firebaseAuth(FirebaseApp app) {
    return FirebaseAuth.getInstance(app);
  }

  @Bean
  Firestore firestore(FirebaseApp app) {
    return FirestoreClient.getFirestore(app);
  }
}
```

**Khởi tạo một lần trong vòng đời JVM.** Đoạn mã dự định một Spring application duy nhất sở hữu default `FirebaseApp`; nếu tests/multiple contexts khởi tạo nhiều apps trong cùng JVM, dùng tên app riêng hoặc cleanup có kiểm soát, không cứ gọi `initializeApp` ở mỗi request. `FirestoreClient.getFirestore(app)` trả cùng Firestore instance gắn với app đó.

### 4.3. OrdersApplication.java và application.properties

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
  public static void main(String[] args) {
    SpringApplication.run(OrdersApplication.class, args);
  }
}
```

```properties
app.firebase.project-id=${GOOGLE_CLOUD_PROJECT:demo-orders}
server.address=0.0.0.0
server.port=${PORT:8080}
```

**Không để `demo-orders` trở thành project production do quên biến môi trường.** Khi triển khai thật, yêu cầu `GOOGLE_CLOUD_PROJECT` được đặt đúng project của Firebase Auth/Firestore và đối chiếu giá trị đã deploy. Với database được đặt tên khác `(default)`, dùng overload `FirestoreClient.getFirestore(app, databaseId)` và IAM/ứng dụng phải nhất quán.

## 5. Xác thực Firebase ID token và kiểm tra chủ sở hữu

Sau khi đăng nhập bằng **Firebase Authentication client SDK**, frontend lấy ID token bằng `currentUser.getIdToken()` và gửi mỗi request HTTPS:

```http
GET /api/orders/EXAMPLE_ORDER_ID HTTP/1.1
Host: api.example.com
Authorization: Bearer FIREBASE_ID_TOKEN_FROM_CLIENT
```

Backend gọi `FirebaseAuth.verifyIdToken(token)` để kiểm tra **chữ ký, thời hạn và Firebase project/audience**, rồi lấy `uid` từ token đã xác minh. **Không lấy `ownerUid` từ query/body để quyết định quyền**. Firebase ID token có thể bị thu hồi/khóa user trước khi hết hạn: `verifyIdToken(token, true)` kiểm tra revocation/disabled user bổ sung nhưng thường phát sinh network call và latency; chọn chính sách cho endpoint nhạy cảm.

Các tình huống phải bị từ chối:

| Request | Kết quả dự kiến |
| --- | --- |
| Không có Bearer token hoặc token sai/expired | `401 Unauthorized` |
| Token Firebase hợp lệ nhưng của **project khác** | `401` do verify thất bại |
| User A đọc đơn của user B | `404` hoặc `403` theo chính sách không tiết lộ |
| Cùng UID nhưng thiếu quyền admin để xem dữ liệu người khác | `403`; không dựa duy nhất vào việc “đã đăng nhập” |
| Google Cloud service-account token truyền như Firebase token | Không được chấp nhận bởi `verifyIdToken` |

Trong ứng dụng nhiều endpoints, nên dùng **Spring Security filter/interceptor** để xác thực token và đặt principal vào SecurityContext, thay vì chép mã xác thực vào từng controller. Mẫu sau dùng helper nhỏ cho dễ hiểu, **không phải một security framework hoàn chỉnh**.

## 6. Backend Java: đặt hàng nguyên tử, chống trùng và đọc đơn

Mô hình document thử:

```text
inventory/
  sku-001
    available: 100

orders/
  <idempotencyKey>
    ownerUid: "<Firebase UID đã xác minh>"
    sku: "sku-001"
    quantity: 2
    status: "CREATED"
    createdAt: <server timestamp>
```

Để ví dụ đơn giản nhưng có thể thử retry, client gửi **Idempotency-Key** ngẫu nhiên duy nhất (chẳng hạn UUID v4 bỏ dấu `-` vẫn hợp lệ), lưu ổn định khi retry cùng một thao tác. Backend dùng key đó làm document ID và **trong cùng transaction** đọc đơn cũ, đọc tồn kho, trừ tồn và tạo đơn. Trong ứng dụng đa tenant quy mô lớn, nên sinh document key từ **hash(uid + operationId)** để không có collision/đoán ID xuyên người dùng; ví dụ lab kiểm tra `ownerUid` và dữ liệu request trước khi trả đơn đã có.

### 6.1. OrdersController.java

```java
package com.example.orders;

import com.google.cloud.firestore.*;
import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.auth.FirebaseAuthException;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.TimeUnit;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/orders")
public class OrdersController {
  private final Firestore db;
  private final FirebaseAuth auth;

  public OrdersController(Firestore db, FirebaseAuth auth) {
    this.db = db;
    this.auth = auth;
  }

  public record CreateOrder(String sku, long quantity) {}

  private String requireUid(String authorization) {
    if (authorization == null || !authorization.startsWith("Bearer ")) {
      throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
    }
    try {
      String token = authorization.substring("Bearer ".length());
      return auth.verifyIdToken(token).getUid();
    } catch (FirebaseAuthException ex) {
      throw new ResponseStatusException(HttpStatus.UNAUTHORIZED,
          "Invalid Firebase ID token");
    }
  }

  @PostMapping
  public ResponseEntity<Map<String, Object>> create(
      @RequestHeader(value = HttpHeaders.AUTHORIZATION, required = false)
          String authorization,
      @RequestHeader("Idempotency-Key") String operationId,
      @RequestBody CreateOrder request) throws Exception {

    String uid = requireUid(authorization);
    if (!operationId.matches("[A-Za-z0-9_-]{8,64}")
        || request.sku() == null
        || !request.sku().matches("[A-Za-z0-9_-]{1,40}")
        || request.quantity() <= 0 || request.quantity() > 100) {
      throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
    }

    DocumentReference orderRef =
        db.collection("orders").document(operationId);
    DocumentReference stockRef =
        db.collection("inventory").document(request.sku());

    String orderId;
    try {
      orderId = db.runTransaction(tx -> {
        // TẤT CẢ reads phải diễn ra trước writes trong Firestore transaction.
        DocumentSnapshot old = tx.get(orderRef).get();
        if (old.exists()) {
          if (!uid.equals(old.getString("ownerUid"))
              || !request.sku().equals(old.getString("sku"))
              || !Objects.equals(request.quantity(), old.getLong("quantity"))) {
            throw new ResponseStatusException(HttpStatus.CONFLICT,
                "Idempotency key already used");
          }
          return orderRef.getId();
        }

        DocumentSnapshot stock = tx.get(stockRef).get();
        Long available = stock.getLong("available");
        if (available == null || available < request.quantity()) {
          throw new ResponseStatusException(HttpStatus.CONFLICT,
              "Insufficient stock");
        }

        tx.update(stockRef, "available", available - request.quantity());
        Map<String, Object> order = new HashMap<>();
        order.put("ownerUid", uid);
        order.put("sku", request.sku());
        order.put("quantity", request.quantity());
        order.put("status", "CREATED");
        order.put("createdAt", FieldValue.serverTimestamp());
        tx.create(orderRef, order);
        return orderRef.getId();
      }).get(20, TimeUnit.SECONDS);
    } catch (java.util.concurrent.ExecutionException ex) {
      // ApiFuture.get() bọc lỗi nghiệp vụ từ transaction callback.
      // Không biến 409 thành 500 do wrapper của Future.
      if (ex.getCause() instanceof ResponseStatusException businessError) {
        throw businessError;
      }
      throw ex; // Production: ControllerAdvice phân loại lỗi Firestore.
    }

    return ResponseEntity.status(HttpStatus.CREATED)
        .body(Map.of("id", orderId, "status", "CREATED"));
  }

  @GetMapping("/{orderId}")
  public ResponseEntity<Map<String, Object>> get(
      @RequestHeader(value = HttpHeaders.AUTHORIZATION, required = false)
          String authorization,
      @PathVariable String orderId) throws Exception {

    String uid = requireUid(authorization);
    if (!orderId.matches("[A-Za-z0-9_-]{8,64}")) {
      throw new ResponseStatusException(HttpStatus.NOT_FOUND);
    }
    DocumentSnapshot doc =
        db.collection("orders").document(orderId)
          .get().get(10, TimeUnit.SECONDS);

    // Không làm lộ sự tồn tại của đơn hàng thuộc người khác.
    if (!doc.exists() || !uid.equals(doc.getString("ownerUid"))) {
      throw new ResponseStatusException(HttpStatus.NOT_FOUND);
    }
    return ResponseEntity.ok(Map.of(
        "id", doc.getId(),
        "sku", doc.getString("sku"),
        "quantity", doc.getLong("quantity"),
        "status", doc.getString("status")));
  }
}
```

### 6.2. Vì sao mẫu này không trừ tồn kho hai lần khi callback retry?

**Firestore transaction có thể chạy lại callback** nếu document đã đọc bị transaction khác thay đổi. Bằng cách đọc **orderRef và stockRef trước khi ghi**, một request có cùng operation ID hoặc một transaction xung đột phải kiểm tra lại trạng thái, thay vì tiếp tục trừ kho trên số lượng cũ.

| Thử nghiệm | Kỳ vọng |
| --- | --- |
| Hai request khác operationId cùng mua SKU cuối | Chỉ transaction đủ tồn kho commit; request còn lại lỗi 409 |
| Gửi lại cùng operationId, cùng payload | Trả cùng order ID; số tồn kho không giảm lần hai |
| Cùng operationId nhưng thay SKU/số lượng/user | Báo xung đột, không cấp quyền/không tạo đơn mới |
| Token hết hạn hoặc UID không khớp document | 401 hoặc 404, không trả dữ liệu người khác |
| Firestore timeout sau commit nhưng client retry cùng key | Có thể trả lại đơn đã tạo, không ghi đè tồn kho |

**Không được gọi payment API, publish Pub/Sub hoặc gửi email trong transaction callback**: callback có thể chạy nhiều lần dù chỉ một transaction cuối cùng commit. Với nghiệp vụ nhiều dịch vụ, ghi **outbox event** trong cùng transaction và phát sau commit, với consumer idempotent. Ví dụ dùng `Idempotency-Key` dạng document ID chỉ minh họa; production cần chống key guessing/collision, giới hạn input, lưu request fingerprint, expiry và audit.

### 6.3. Xử lý lỗi production

Đoạn controller giữ ngắn để tập trung vào Firestore và Auth; nó chưa có `@ControllerAdvice` để phân loại `ExecutionException`, `TimeoutException`, `RESOURCE_EXHAUSTED`, `UNAVAILABLE`, `FAILED_PRECONDITION`, HTTP rate limits và trace correlation. Trên production hãy:

- Phân biệt `400/401/403/404/409` (client/business) với `503/504` (backend tạm lỗi).
- Không trả stack trace, document body nhạy cảm hoặc access token cho client.
- Không retry nguyên POST với **operationId mới** khi kết quả commit chưa rõ; kiểm tra operationId cũ trước.
- Đặt request deadline phù hợp, giới hạn concurrency để tránh bão kết nối/transactions.
- Có test race condition và endpoint authorization, không chỉ test đường thành công.

## 7. Query dữ liệu theo người dùng, phân trang và index

Một danh sách đơn hàng có thể lọc `ownerUid` rồi sắp theo `createdAt` giảm dần. **Bắt buộc dùng UID từ Firebase token đã xác minh**, không cho client tự nhập UID cần đọc:

```java
// Bên trong controller/service, đã có Firestore db và verified uid.
Query firstPage = db.collection("orders")
    .whereEqualTo("ownerUid", uid)
    .orderBy("createdAt", Query.Direction.DESCENDING)
    .limit(20);

QuerySnapshot first = firstPage.get().get(10, TimeUnit.SECONDS);
for (QueryDocumentSnapshot doc : first.getDocuments()) {
  // Map sang response DTO; không trả toàn bộ fields không cần thiết.
  System.out.println(doc.getId());
}

// Khi có ít nhất một document, lấy trang kế tiếp bằng cursor:
if (!first.getDocuments().isEmpty()) {
  QueryDocumentSnapshot last =
      first.getDocuments().get(first.size() - 1);
  Query nextPage = firstPage.startAfter(last);
  QuerySnapshot second = nextPage.get().get(10, TimeUnit.SECONDS);
}
```

Đây là **trích đoạn Java minh họa**, không phải method REST hoàn chỉnh. Kết hợp `whereEqualTo + orderBy` có thể yêu cầu **composite index**; khi query fail với index error, Firestore cung cấp hướng dẫn tạo index. Index phải được quản lý bằng IaC/CI và chờ build trước khi đổi traffic. `orderBy("createdAt")` chỉ trả documents có field này; đối với dữ liệu cũ, backfill có kế hoạch.

Đừng dùng `offset` lớn cho pagination: Firestore có thể vẫn tính phí các documents bị bỏ qua. Cursor dùng `startAfter(lastSnapshot)` hiệu quả hơn, nhưng vẫn cần xử lý danh sách thay đổi trong lúc người dùng phân trang. Luôn giới hạn page size và fields trả về; không tải cả collection vào RAM để lọc.

## 8. Chạy local với Firebase Emulator Suite

Firebase emulators cho phép thử **Firestore/Auth trong máy phát triển** mà không dùng dữ liệu production. Firestore emulator mặc định ở `127.0.0.1:8080`, Auth emulator thường ở `127.0.0.1:9099`; Spring Boot sẽ chạy **port 8081** để không tranh cổng.

### 8.1. Chuẩn bị một lần và khởi chạy

```bash
# THAO TÁC TRONG DỰ ÁN LAB, không sửa file/module production.
# Cài Firebase CLI theo tài liệu; chạy firebase init emulators một lần
# để chọn Firestore + Authentication và tạo firebase.json.
firebase init emulators

# Terminal 1: emulator với project ID giả lập, không dùng project thật.
firebase emulators:start --only firestore,auth --project demo-orders
```

Trong terminal backend:

```bash
# Terminal 2: chỉ sử dụng các biến này trên MÁY LOCAL.
export GOOGLE_CLOUD_PROJECT="demo-orders"
export FIRESTORE_EMULATOR_HOST="127.0.0.1:8080"
export FIREBASE_AUTH_EMULATOR_HOST="127.0.0.1:9099"
export PORT=8081

# FirebaseConfiguration vẫn lấy ADC; chuẩn bị local ADC hợp lệ
# bằng gcloud auth application-default login nếu máy chưa có.
./mvnw -B spring-boot:run
```

Biến `FIRESTORE_EMULATOR_HOST` **không chứa `http://`**. Khi bật `FIREBASE_AUTH_EMULATOR_HOST`, Admin SDK chấp nhận ID token **không ký** của Auth emulator để kiểm thử: **tuyệt đối không đặt biến này trong Cloud Run/GKE production**. Luôn đối chiếu project ID của emulator, Admin SDK và Firebase client. Nếu service không khởi động do thiếu ADC, dùng ADC cho phát triển tại máy; không tạo một service account key dài hạn chỉ để khởi động emulator.

### 8.2. Tạo dữ liệu tồn kho thử

Có thể tạo `inventory/sku-001` với integer field `available=5` qua **Firestore emulator UI**, hoặc dùng REST API nội bộ của emulator:

```bash
# CHỈ GHI VÀO EMULATOR trên localhost; không gọi Firestore production.
curl -sS -X PATCH \
  "http://127.0.0.1:8080/v1/projects/demo-orders/databases/(default)/documents/inventory/sku-001" \
  -H "Content-Type: application/json" \
  -d '{"fields":{"available":{"integerValue":"5"}}}'
```

### 8.3. Tạo Firebase user thử và gọi backend

Sử dụng giao diện **Authentication emulator** hoặc REST API emulator để tạo user giả. Ví dụ REST:

```bash
# CHỈ AUTH EMULATOR, KHÔNG DÙNG THÔNG TIN ĐĂNG NHẬP THẬT.
curl -sS -X POST \
  "http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1/accounts:signUp?key=demo-key" \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.test","password":"demo-password-12345","returnSecureToken":true}'
```

Response có `idToken` giả lập; lấy token đó vào biến `FIREBASE_ID_TOKEN` trong terminal cá nhân, **không in/log token vào tài liệu hoặc commit**. Dùng một ID token thật của **Firebase client SDK** khi chạy ngoài emulator, không dùng `gcloud auth print-identity-token` thay thế:

```bash
# CHỈ GỌI BACKEND LOCAL, sử dụng token từ Auth emulator.
OPERATION_ID="order-demo-0001"

curl -sS -X POST "http://127.0.0.1:8081/api/orders" \
  -H "Authorization: Bearer $FIREBASE_ID_TOKEN" \
  -H "Idempotency-Key: $OPERATION_ID" \
  -H "Content-Type: application/json" \
  -d '{"sku":"sku-001","quantity":2}'

curl -sS "http://127.0.0.1:8081/api/orders/$OPERATION_ID" \
  -H "Authorization: Bearer $FIREBASE_ID_TOKEN"
```

Đọc lại tồn kho trong emulator: `available` từ 5 xuống 3. Gọi lại **cùng operation ID và cùng payload** không được làm số tồn giảm còn 1. Gọi bằng ID token của **user khác** không được xem order. Nếu thiếu token hoặc `FIREBASE_AUTH_EMULATOR_HOST` không khớp emulator, backend phải trả 401.

### 8.4. Firestore Security Rules khác kiểm thử Admin SDK

Nếu web/mobile truy cập Firestore trực tiếp, có thể dùng một quy tắc *chỉ đọc đơn của chính mình*:

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /orders/{orderId} {
      allow read: if request.auth != null
                  && request.auth.uid == resource.data.ownerUid;
      allow write: if false;
    }
    match /{document=**} {
      allow read, write: if false;
    }
  }
}
```

Đây là chính sách dành cho **Firebase web/mobile SDK**. Để test Rules, dùng client SDK hoặc `@firebase/rules-unit-testing` với Firestore emulator và mô phỏng `auth.uid`. **Admin SDK sẽ bypass rules kể cả khi kết nối emulator**; không thể kết luận Security Rules an toàn chỉ vì bài test Java server hoạt động.

## 9. Triển khai Cloud Run và IAM tối thiểu

Trên Cloud Run, service account runtime cần quyền Firestore (thường `roles/datastore.user` cho thao tác đọc/ghi). Đây là role rộng ở mức dữ liệu DB; nó **không tự giới hạn theo document ownerUid**. Hạn chế quyền trên project/database phù hợp và giữ authorization trong backend; nếu chỉ đọc, cân nhắc role read-only.

Ví dụ Bash minh họa, **có thay đổi IAM và dịch vụ trả phí**:

```bash
PROJECT_ID="orders-lab"
REGION="asia-southeast1"
RUNTIME_SA="orders-api@$PROJECT_ID.iam.gserviceaccount.com"

gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  cloudbuild.googleapis.com \
  --project="$PROJECT_ID"

gcloud iam service-accounts create orders-api \
  --project="$PROJECT_ID" \
  --display-name="Orders Firebase backend runtime"

# Cấp quyền đọc/ghi Firestore cho đúng runtime identity.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/datastore.user"

# THAY ĐỔI / PHÁT SINH PHÍ: build/deploy source nếu dự án đã có
# Firebase Auth, Firestore, Maven project và Cloud Build permissions.
gcloud run deploy orders-backend \
  --source=. \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --service-account="$RUNTIME_SA" \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID" \
  --allow-unauthenticated
```

`--allow-unauthenticated` chỉ cho phép request HTTP tới Cloud Run **mà không cần Google IAM Invoker token**. Các endpoints `/api/orders` của ví dụ **vẫn phải có Firebase ID token hợp lệ và tự kiểm tra ownerUid**. Với hệ thống không muốn mở ingress công khai, cấu hình Cloud Run private và dùng caller Google identity/API Gateway/Load Balancer phù hợp; **Firebase ID token một mình không thay `roles/run.invoker`**. Thêm rate limiting, CORS allowlist, App Check và Cloud Armor khi threat model yêu cầu.

Nếu service account hoặc APIs đã tồn tại, kiểm tra trước khi tạo/cấp lại; nên quản trị tài nguyên qua IaC. Cloud Run source deployment yêu cầu **build identity** có quyền riêng để build/push; không cấp Editor toàn project chỉ để qua lỗi build. Không đặt `FIREBASE_AUTH_EMULATOR_HOST` hay `FIRESTORE_EMULATOR_HOST` trong production; nếu có, backend có thể kết nối sai nguồn hoặc chấp nhận token thử nghiệm.

## 10. App Check, custom claims và phân quyền nghiệp vụ

**Firebase Authentication** xác minh **ai** đang gọi; **App Check** giúp xác minh request có nguồn từ ứng dụng được đăng ký (chống lạm dụng ở mức bổ sung); **authorization** quyết định người đó được làm gì. Ba chức năng không thay thế nhau.

Firebase Admin Java **9.12.0+** hỗ trợ `FirebaseAppCheck.verifyToken()` và tùy chọn **replay protection** cho endpoints nhạy cảm:

```java
// Trích đoạn trong HTTP filter của Spring Boot:
String appCheckToken = request.getHeader("X-Firebase-AppCheck");
if (appCheckToken == null || appCheckToken.isBlank()) {
  response.sendError(401);
  return;
}
FirebaseAppCheck.getInstance(firebaseApp).verifyToken(appCheckToken);
// Tiếp tục xác thực Firebase ID token và kiểm tra quyền nghiệp vụ.
```

Mẫu trên **thiếu imports/exception handling và chưa phải filter hoàn chỉnh**. Khi dùng replay protection, phải cấp quyền và kiểm tra `isAlreadyConsumed()` như tài liệu quy định, đồng thời client lấy **limited-use token**. Đừng bật chế độ consume cho mọi request mà không đánh giá latency/cost.

Với admin role, Firebase custom claims có thể mang `admin=true`, nhưng chỉ **server đáng tin cậy** được set claims; kiểm tra giá trị từ ID token đã được verify và cân nhắc token refresh/revocation. **Không chấp nhận field `role: "admin"` trong request JSON**. Với multi-tenant, backend vẫn phải kiểm tra quyền truy cập tenant hiện tại, không chỉ boolean role.

## 11. Độ tin cậy, observability và chi phí

### 11.1. Tín hiệu cần theo dõi

| Tín hiệu | Tình huống lỗi | Cách xử lý |
| --- | --- | --- |
| HTTP `401/403` | ID token sai, hết hạn hoặc thiếu quyền | Kiểm tra Firebase project, token audience, Auth/emulator flags |
| HTTP `404` | Order không tồn tại hoặc không thuộc UID | Không lộ dữ liệu document người khác |
| Firestore `ABORTED` | Transaction tranh chấp cùng inventory doc | Retry tự động có giới hạn; giảm hotspot |
| `RESOURCE_EXHAUSTED` / `UNAVAILABLE` | Quota, peak traffic, network/API lỗi | Rate limit, backoff và theo dõi SLO |
| p95 latency & Firestore reads/writes | N+1 queries, indexes/region không phù hợp | Tối ưu query, pagination và data model |
| Firestore reads/writes/index storage | Chi phí tăng sau rollout | Giới hạn page size, tránh reads không cần, loại index thừa |
| Cloud Run CPU/memory/concurrency | Cạnh tranh tài nguyên hoặc nghẽn request threads | Giới hạn concurrency, dùng async khi phù hợp |

Ghi logs có cấu trúc với `requestId`, `operationId` đã được xử lý an toàn, collection/operation name, error code và latency; **không log Firebase ID token, refresh token, mật khẩu, UID gốc hoặc document payload nhạy cảm** nếu chính sách không cho phép. Đặt alerts theo error rate, p95 và quota, không chỉ theo số lượng Pods.

### 11.2. Tính chi phí đúng

Firestore tính phí theo **document reads/writes/deletes, index-entry reads trong những loại query liên quan, storage, network và các tính năng được bật**. Transactions có thể đọc/ghi lại khi retry; pagination bằng `offset` lớn làm tăng billed reads, trong khi queries trên các fields có index giúp giảm công việc scan.

- Chỉ lưu các field thật cần truy vấn; fields lớn hoặc arrays thường làm index/storage tăng nhanh.
- Tránh document “hotspot” (ví dụ một `inventory/sku-001` nhận quá nhiều concurrent orders); cân nhắc reservation/sharding và kiểm chứng tính đúng trước khi scale.
- Dùng TTL cho dữ liệu tạm khi phù hợp, nhớ **TTL deletes có tính phí** và không nên dựa vào TTL để xóa ngay lập tức.
- Với thay đổi hàng loạt, xem **BulkWriter/batches** và giới hạn hiện hành thay vì một transaction khổng lồ.
- Dùng Billing budgets/alerts theo project, áp quotas/rate limits để ngăn thử nghiệm tạo traffic ngoài ý muốn.

**Không xem Firestore như một cache miễn phí**: mỗi lần truy vấn/đọc có thể tính phí, kể cả query trả ít kết quả theo các đơn vị tính của dịch vụ. Cân nhắc dữ liệu quan hệ phức tạp/joins, analytics diện rộng hoặc transactions rất nóng có thể phù hợp Cloud SQL, AlloyDB, Spanner hoặc BigQuery hơn tùy yêu cầu.

## 12. Tình huống thực tế: đơn hàng cuối cùng trong kho

Tồn kho `inventory/sku-001.available = 1`. Hai người dùng hợp lệ, A và B, đồng thời gửi `POST /api/orders` mua mỗi người một sản phẩm.

```mermaid
sequenceDiagram
  participant A as User A
  participant B as User B
  participant API as Spring Boot
  participant DB as Firestore transaction
  A->>API: POST (operationId A, qty 1)
  B->>API: POST (operationId B, qty 1)
  API->>DB: T1 read inventory.available = 1
  API->>DB: T2 read inventory.available = 1
  DB-->>API: T1 commit: available=0 + order A
  DB-->>API: T2 conflict; rerun callback
  API->>DB: T2 re-read available=0
  DB-->>B: Order B rejected: insufficient stock
  API-->>A: Order A created
```

**Kết quả kỳ vọng:** chỉ một đơn được tạo và số tồn không âm. Nếu transaction callback có gọi API thanh toán, **việc chạy lại có thể charge nhiều lần**; phải tách payment và dùng idempotency/outbox hoặc workflow bù trừ. Đây là một lý do Firestore transaction bảo vệ dữ liệu Firestore nhưng **không tự trở thành distributed transaction của mọi dịch vụ**.

### 12.1. Kịch bản kiểm thử

| Test | Điều kiện | Kết quả đạt |
| --- | --- | --- |
| Đơn mới | Token A hợp lệ; tồn kho đủ | 201, tạo order với `ownerUid=A`, tồn giảm một lần |
| Request lặp | Cùng token, key và payload | Trả cùng order ID, tồn không giảm nữa |
| Key bị sử dụng lại | Cùng key nhưng payload khác hoặc UID khác | 409, không cấp quyền dữ liệu |
| Hai giao dịch cạnh tranh | Hai keys khác nhau, hàng còn một | Một thành công, một báo thiếu hàng |
| Người dùng B đọc đơn A | Token B hợp lệ, ID đơn A | 404/403, không trả thông tin order |
| Token hết hạn | Bearer token sai | 401; không có Firestore write |
| Firestore không sẵn sàng | API backend lỗi tạm thời | 503/504 được phân loại, giữ idempotency key khi retry |
| Client dùng Firestore SDK trực tiếp | Rules chỉ cho đọc đúng UID | Bị từ chối khi đọc order người khác |

### 12.2. Checklist production ngoài ví dụ

Ứng dụng thực tế cần thêm **authorization middleware**, validation bằng Jakarta Bean Validation, logging/trace correlation, timeout/rate limit, exception handler, automated tests, index migrations, rollback, monitoring và kiểm soát dữ liệu cá nhân. Nếu có nghiệp vụ thanh toán, phải lưu **payment state machine**, chống chuyển trạng thái sai và bảo đảm webhook/events idempotent; không xem một document `status="CREATED"` là bằng chứng thanh toán đã hoàn tất.

## 13. Lỗi thường gặp và hướng chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `FirebaseApp with name [DEFAULT] already exists` | Khởi tạo Admin SDK nhiều lần trong cùng JVM | Tạo app một lần bằng Spring bean, cleanup tests |
| `Unable to determine Project ID` | ADC không mang project, env sai | Set project ID rõ trong `FirebaseOptions`, kiểm tra runtime identity |
| Backend trả 401 với Firebase token thật | Sai Firebase project, token hết hạn, nhầm custom/Google ID token | Kiểm tra issuer/audience/SDK sign-in, đồng bộ project ID |
| Emulator token bị chấp nhận ở môi trường thật | `FIREBASE_AUTH_EMULATOR_HOST` bị đưa lên production | Xóa biến và thêm startup config guard |
| Firestore `PERMISSION_DENIED` | Runtime service account thiếu role dữ liệu | IAM scope đúng project/database và ADC principal |
| Security Rules cấm nhưng Admin SDK vẫn ghi | Server SDK **bypass rules theo thiết kế** | Kiểm tra IAM, backend authorization và API test |
| `FAILED_PRECONDITION: index required` | Query kết hợp filter/order chưa có composite index | Tạo index theo error link/IaC, đợi build |
| Đơn hàng tạo hai lần sau HTTP retry | Client đổi operationId sau timeout | Giữ same idempotency key, kiểm tra stored request fingerprint |
| `ABORTED` cao ở inventory doc | Nhiều giao dịch tranh chấp một document | Đo contention, điều tiết requests, thiết kế reservation hợp lý |
| Không thấy dữ liệu emulator | Sai port/project ID hoặc thiếu `FIRESTORE_EMULATOR_HOST` | Kiểm tra env ngay trước khi start JVM |
| List trả ít document hơn dự kiến | Query `orderBy` loại documents thiếu field, pagination/filter | Kiểm tra schema/index, cursor và dữ liệu cũ |
| Firestore bills tăng | Query vô hạn, index entries, logs, repeated reads/retries | Query Explain/usage metrics, giới hạn trang, Billing alerts |

## 14. Bài tập thực hành

### Bài A — Khởi tạo đúng danh tính

Giải thích vì sao backend Java dùng ADC trên Cloud Run và client mobile dùng Firebase Auth client SDK. Chỉ ra ba lỗi khi đưa service account JSON vào mobile app hoặc dùng Firebase custom token trực tiếp làm Bearer token của API.

### Bài B — Firestore Emulator

Chạy Auth/Firestore emulators với `demo-orders`, tạo `inventory/sku-001.available=5`, tạo user thử, gọi `POST /api/orders` với token giả lập. Kiểm tra document được ghi đúng chủ sở hữu. Vì sao không dùng project production cho lệnh emulator?

### Bài C — Phân quyền theo UID

Tạo hai users trong Auth emulator. User A đặt đơn, user B biết được orderId. Viết kiểm thử xác minh backend không trả dữ liệu đơn của A. Giải thích vì sao chỉ viết Firestore Security Rules là không đủ nếu API Java dùng Admin SDK.

### Bài D — Transaction và retry

Tồn kho chỉ còn một sản phẩm. Mô phỏng hai POST cùng lúc với hai operation IDs. Kiểm tra chỉ một đơn được commit. Lặp lại cùng key: vì sao không giảm tồn kho lần thứ hai? Điều gì xảy ra nếu gửi email ngay trong callback transaction?

### Bài E — Query và index

Viết Java query lọc `ownerUid`, sắp `createdAt DESC` và lấy 20 đơn. Thử bỏ index tổng hợp hoặc cố đọc quá nhiều hàng. Chỉ ra khi nào cần composite index và vì sao nên phân trang bằng cursor.

### Bài F — Firebase ID token và App Check

Thiết kế filter bảo vệ endpoint đặt hàng: xác minh Firebase ID token, từ chối người dùng bị khóa theo policy, kiểm tra App Check nếu có và bảo đảm principal/UID được truyền tới service. Chỉ ra phần nào là **authentication**, **app attestation** và **authorization**.

### Bài G — Cloud Run và least privilege

Thiết kế runtime service account chỉ có quyền đọc/ghi Firestore cần thiết; giải thích khi nào Cloud Run service public HTTP ingress vẫn có thể bảo vệ bằng Firebase Auth và khi nào cần thêm Google IAM Invoker. Nêu hai biến emulator tuyệt đối không được set trên production.

### Bài H — SLO và chi phí

Ứng dụng có 100.000 người dùng, mỗi người mở danh sách đơn 10 lần/ngày. Ước lượng số document reads theo kích thước trang và cache strategy; đề xuất pagination, index, budget alerts và cách thử concurrency hotspot ở một SKU. Chọn tối đa sáu tín hiệu monitoring để phát hiện regression.

### Câu hỏi tự kiểm tra

1. Firebase Admin SDK Java và Firebase Web SDK khác nhau về nơi chạy và quyền gì?
2. Backend dùng Firestore server SDK có áp dụng Firestore Security Rules không?
3. Firebase ID token và custom token khác nhau thế nào?
4. Một ID token hợp lệ có tự cho quyền đọc mọi orders không?
5. Vì sao dùng operation ID ổn định khi POST có thể được retry?
6. Trong Firestore transaction, thứ tự đọc/ghi và callback retry có ràng buộc gì?
7. Khi nào cần composite index và cursor-based pagination?
8. Vì sao không được bật Auth emulator flags trên Cloud Run production?
9. `roles/datastore.user` và `ownerUid` kiểm soát quyền ở những tầng nào?
10. App Check có thay Firebase Authentication hoặc authorization không?

## 15. Checklist và tài liệu chính thức

- [ ] Firebase project và Firestore database đúng mode, ID, region, Billing.
- [ ] Java 21, Spring Boot, Firebase Admin SDK được kiểm tra phiên bản và dependencies.
- [ ] Admin SDK khởi tạo một lần bằng ADC; Cloud Run/GKE dùng workload service account.
- [ ] Firebase ID token được verify, UID dùng để kiểm tra quyền từng document.
- [ ] Transaction giữ tồn kho và order nguyên tử; có idempotency key ổn định.
- [ ] Query có giới hạn, cursor, indexes cần thiết và tránh hotspot documents.
- [ ] Auth/Firestore emulator tests gồm lỗi token, cross-user read, retry và concurrency.
- [ ] Firestore Security Rules cho clients và IAM/authorization backend được kiểm thử **riêng**.
- [ ] Không dùng emulator flags/secrets trong production; có log an toàn, SLO và Billing alerts.

Tài liệu Firebase và Google Cloud:

- [Firebase Admin SDK Java setup](https://firebase.google.com/docs/admin/setup)
- [Firebase Admin Java release notes](https://firebase.google.com/support/release-notes/admin/java)
- [Firestore server client quickstart](https://firebase.google.com/docs/firestore/quickstart-server)
- [FirestoreClient Java API](https://firebase.google.com/docs/reference/admin/java/reference/com/google/firebase/cloud/FirestoreClient)
- [Verify Firebase ID tokens](https://firebase.google.com/docs/auth/admin/verify-id-tokens)
- [Detect revoked sessions](https://firebase.google.com/docs/auth/admin/manage-sessions)
- [Firestore transactions and batched writes](https://firebase.google.com/docs/firestore/manage-data/transactions)
- [Query data and indexes](https://firebase.google.com/docs/firestore/query-data/indexing)
- [Firestore query cursors](https://firebase.google.com/docs/firestore/query-data/query-cursors)
- [Security Rules with emulator](https://firebase.google.com/docs/firestore/security/test-rules-emulator)
- [Connect Firestore emulator](https://firebase.google.com/docs/emulator-suite/connect_firestore)
- [Connect Auth emulator](https://firebase.google.com/docs/emulator-suite/connect_auth)
- [Verify App Check tokens from backend](https://firebase.google.com/docs/app-check/custom-resource-backend)
- [Firestore server IAM](https://cloud.google.com/firestore/native/docs/security/iam)
- [Firestore best practices](https://firebase.google.com/docs/firestore/best-practices)
- [Cloud Run deploy Java from source](https://cloud.google.com/run/docs/quickstarts/build-and-deploy/deploy-java-service)
- [Firestore pricing](https://cloud.google.com/firestore/pricing)

**Ghi nhớ:** Client xác thực bằng Firebase Auth, Java backend dùng **Firebase Admin SDK/ADC** để xác minh ID token và truy cập Firestore với IAM. Vì **server SDK bỏ qua Security Rules**, backend phải tự kiểm tra quyền truy cập từng document. Dùng transactions và idempotency keys cho nghiệp vụ nhạy cảm, kiểm thử bằng emulators, quan sát SLO/chi phí và không để cấu hình emulator hoặc service account keys lọt vào production.
