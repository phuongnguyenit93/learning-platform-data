# Firebase Authentication và Identity Platform

> **Chương:** Firestore và Firebase  
> **Bài học:** Firebase Authentication và Identity Platform  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học khám phá Google Cloud từ project, IAM, VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu; đồng thời học cách lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và giám sát độ tin cậy, chi phí. Đối với ứng dụng Java có giao diện web/mobile, **xác thực người dùng cuối** là lớp riêng với **danh tính service account của backend**.

**Firebase Authentication** giúp ứng dụng đăng nhập người dùng bằng email/mật khẩu, Google và các nhà cung cấp được hỗ trợ, số điện thoại hoặc custom authentication; Firebase client SDK quản lý phiên đăng nhập và cung cấp **Firebase ID token**. **Identity Platform** là nền tảng nhận dạng khách hàng (CIAM) trên Google Cloud, đồng thời là backend của **Firebase Authentication with Identity Platform** sau khi nâng cấp. Ngoài các cách đăng nhập cơ bản, Identity Platform bổ sung **SAML, OIDC, đa yếu tố (MFA), multi-tenancy, blocking functions và các lựa chọn enterprise**.

Quy tắc quan trọng nhất: **xác thực thành công không đồng nghĩa được phép đọc hoặc sửa mọi dữ liệu**. Java API phải xác minh token và kiểm tra quyền nghiệp vụ; Firebase client truy cập Firestore phải tuân **Security Rules**; Java server SDK truy cập Firestore dùng **Google Cloud IAM**, không bị Security Rules giới hạn. Các ví dụ trong bài chỉ sử dụng project và người dùng thử. Không bật provider, thay IAM, gửi SMS hoặc tạo người dùng thật ngoài sandbox khi chưa được phê duyệt.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt **Firebase Authentication**, **Firebase Authentication with Identity Platform**, **Identity Platform**, **Google Cloud IAM** và **Firebase App Check**.
2. Giải thích đăng nhập → **ID token / refresh token** → xác thực tại Java backend → **domain authorization**.
3. Chọn email/password, social/OAuth, phone, anonymous, custom token, OIDC hay SAML theo yêu cầu.
4. Sử dụng **Firebase Web SDK** để đăng nhập và gửi **ID token qua HTTPS** đến Java API.
5. Khởi tạo **Firebase Admin Java SDK bằng ADC** và kiểm tra `verifyIdToken`/revocation an toàn.
6. Phân biệt **custom token** với **Firebase ID token**, session cookie, custom claims và quyền Google Cloud IAM.
7. Thiết kế Firestore Security Rules theo `request.auth.uid`, hiểu giới hạn của server SDK.
8. Nhận diện nhu cầu **MFA, multi-tenancy, blocking functions** trước khi nâng cấp lên Identity Platform.
9. Xử lý lỗi 401/403, sai project/tenant, token cũ, quota và tính phí MAU/SMS.
10. Lập kế hoạch triển khai, kiểm thử và thu hồi quyền với ví dụ Orders API Java.

## 2. Kiến trúc xác thực cho ứng dụng Java + Firebase

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant Web as Firebase Web/Mobile SDK
    participant Auth as Firebase Auth / Identity Platform
    participant Java as Cloud Run Java Orders API
    participant DB as Firestore
    U->>Web: Nhập phương thức đăng nhập
    Web->>Auth: Xác thực với provider
    Auth-->>Web: Firebase ID token + refresh token
    Web->>Java: HTTPS Authorization: Bearer ID_TOKEN
    Java->>Java: Verify signature, project, expiry, optional revocation
    Java->>Java: Kiểm tra uid, tenant, role và quyền order
    Java->>DB: Server SDK bằng runtime service account + IAM
    DB-->>Java: Dữ liệu được phép theo IAM
    Java-->>Web: JSON / 401 / 403
~~~

### 2.1. Bốn danh tính không được nhầm

| Thành phần | Danh tính | Cơ chế kiểm tra |
|---|---|---|
| **Người dùng cuối** | Firebase `uid` trong ID token | Firebase Authentication / Identity Platform |
| **Client mobile/web** | Firebase app configuration và App Check token nếu bật | Firebase App Check xác minh app/device, **không thay user auth** |
| **Java Cloud Run service** | Runtime **service account** | Google Cloud IAM khi gọi Firestore, Pub/Sub, Cloud SQL... |
| **Developer/CI deployer** | Human/CI principal | IAM deploy, service account impersonation và audit |

**Firebase `uid` không phải email service account.** Một người dùng đăng nhập bằng Google vẫn không tự có quyền `roles/datastore.user` hay `roles/run.invoker` trong project. Ngược lại, Java runtime SA có quyền Firestore **không chứng minh một caller HTTP được phép xem đơn hàng của tenant khác**.

### 2.2. Hai đường tới Firestore

~~~mermaid
flowchart LR
    User["Mobile/Web client"] --> Auth["Firebase Authentication"]
    Auth --> Rules["Firestore Security Rules"]
    Rules --> Firestore["Firestore Native database"]
    API["Java backend"] --> Verify["Verify Firebase ID token<br/>+ business authorization"]
    Verify --> IAM["Runtime SA + Google IAM"]
    IAM --> Firestore
~~~

- **Client SDK Firebase**: Security Rules dùng `request.auth`, các điều kiện document và dữ liệu mới/hiện tại để quyết định truy cập.
- **Firebase Admin SDK / Google Cloud server SDK**: có đặc quyền theo **IAM**; **bypass Security Rules**. Trách nhiệm xác thực caller và authorization nằm ở Java API.
- **Datastore-mode hoặc MongoDB-compatible access**: không tự áp mô hình Firebase Rules như Native client SDK; đánh giá bảo mật theo API/mode riêng.

Không đặt Rules `allow read, write: if false` rồi kết luận Java server không thể đọc dữ liệu; cũng không cấp IAM cho Cloud Run rồi kỳ vọng điện thoại tự truy cập Firestore bằng quyền server.

## 3. Chọn Firebase Authentication hay Identity Platform?

| Tiêu chí | Firebase Authentication cơ bản | Firebase Authentication with Identity Platform / Identity Platform |
|---|---|---|
| Email/password, social, phone, anonymous, custom auth | Có | Có |
| Firebase Client SDK, Admin SDK | Có | Có; giữ tương thích với ứng dụng đã dùng Firebase |
| SAML / generic OpenID Connect | Không theo tập tính năng cơ bản | Có |
| MFA (SMS, TOTP theo điều kiện hỗ trợ) | Không có tính năng nâng cao tương đương | Có |
| Tách danh tính **multi-tenant** trong một project | Không | Có |
| **Blocking functions** trước tạo user/đăng nhập | Không | Có |
| Identity-Aware Proxy integration | Không theo bản cơ bản | Có ở Identity Platform |
| SLA enterprise / BAA coverage | Không theo gói cơ bản | Có theo điều kiện dịch vụ/thoả thuận |
| Giá | Theo Firebase plan và provider/quota | Thường theo **Monthly Active Users**; SMS/MFA tính riêng |
| Đội phù hợp | App consumer nhỏ/vừa, không cần federation nâng cao | B2B, SaaS nhiều tenants, enterprise SSO, quy định bảo mật |

Đây là so sánh **định hướng**, không khẳng định mọi MFA provider, vùng, compliance/SLA hay gói giá được bật tự động. Khi bật **Firebase Authentication with Identity Platform**, app **thường tiếp tục dùng SDK cũ mà không cần di chuyển users**, nhưng **billing/quota thay đổi**; cần xem giá/giới hạn trước nâng cấp. Tích hợp thêm SAML/OIDC, MFA hoặc tenant-aware flows **vẫn phải viết cấu hình và code mới**.

### 3.1. Ba trường hợp điển hình

1. **Mobile theo dõi order** có login Google/email, một user pool và không có SSO doanh nghiệp: bắt đầu từ Firebase Authentication cơ bản.
2. **Ứng dụng đối tác B2B** yêu cầu SAML với nhà cung cấp danh tính riêng: cân nhắc Identity Platform để hỗ trợ enterprise federation.
3. **SaaS Java phục vụ nhiều khách hàng tổ chức**, mỗi khách hàng muốn user pool/provider/policies riêng: Identity Platform multi-tenancy đáng đánh giá.

Không nâng cấp chỉ vì muốn một Java API trên Cloud Run: Firebase Authentication cơ bản **đã cho phép** Java Admin SDK xác minh Firebase ID token.

## 4. Các phương thức đăng nhập và tiêu chí lựa chọn

| Provider | Dùng khi | Bảo mật/vận hành cần chú ý |
|---|---|---|
| **Email/password** | Sản phẩm muốn quản lý tài khoản trực tiếp | Email verification, password reset, credential-stuffing protection |
| **Email link / passwordless** | Muốn giảm mật khẩu | Authorized domain, chống phishing và email delivery |
| **Google/Apple/Facebook/GitHub...** | Social login | OAuth consent, redirect URI, account linking |
| **Phone/SMS** | Tính năng dựa số điện thoại hoặc bước xác minh | Phí SMS, quota, SIM-swap, abuse prevention |
| **Anonymous** | Khách trải nghiệm trước khi tạo tài khoản | Account linking, cleanup, không coi anonymous là danh tính đáng tin cho giao dịch |
| **Custom auth** | Có hệ thống identity riêng và muốn liên kết Firebase | Chỉ backend đáng tin được ký custom token; client exchange lấy ID token |
| **SAML 2.0** | Enterprise SSO với IdP tổ chức | Metadata, certificates, assertion audience, clock skew |
| **Generic OIDC** | Enterprise SSO/third-party IdP dùng OIDC | Issuer, client ID, redirect, scopes, JWKS, account linking |

**Phone/SMS không nên là bằng chứng danh tính duy nhất cho tài khoản giá trị cao**: số điện thoại có thể chuyển chủ và bị SIM-swap. **Email/password** cần thiết lập email enumeration protection, password policy và rate limiting phù hợp. Với social/OIDC/SAML, thiết kế **account linking** để một người dùng đăng nhập bằng hai provider không vô tình tạo hai hồ sơ business khác nhau.

### 4.1. Khi nào dùng custom authentication?

Một backend Java đã có hệ thống đăng nhập riêng có thể cấp **Firebase custom token**:

~~~text
Backend Java xác minh credential nghiệp vụ
  → Firebase Admin SDK createCustomToken(uid)
  → Client signInWithCustomToken(customToken)
  → Firebase Auth trả Firebase ID token + refresh token
  → Client dùng ID token truy cập Firebase / Java API
~~~

**Custom token không phải Firebase ID token.** Không chuyển custom token nguyên bản vào `FirebaseAuth.verifyIdToken()` để cấp quyền API; nó phải được client đổi qua Firebase Authentication trước. Việc ký custom token bằng Admin SDK có thể cần quyền IAM **signBlob/token signing** của service identity trong môi trường Google Cloud; **không** tải service account JSON key xuống chỉ vì cần chức năng này.

## 5. ID token, refresh token và session cookie

| Loại token | Ai phát hành / dùng | Thời gian & lưu ý |
|---|---|---|
| **Firebase ID token** | Firebase Authentication trả sau sign-in | JWT thường có hiệu lực khoảng **1 giờ**, dùng cho Security Rules hoặc Java API verify |
| **Refresh token** | Client SDK quản lý phiên dài hạn | Dùng lấy ID token mới; bị vô hiệu trong những tình huống như account disable/delete/major change hoặc admin revoke |
| **Custom token** | Backend Admin SDK tạo để client sign-in | Chỉ để **đổi** sang Firebase session, không dùng làm bearer token của API |
| **Firebase session cookie** | Admin SDK tạo từ ID token cho web server session | Tuỳ chọn khoảng **5 phút đến 2 tuần**, `HttpOnly`/`Secure`, chống CSRF |
| **OIDC token của Cloud Run service caller** | Google Cloud IAM/service-to-service | Dùng invoke Cloud Run private, **khác** Firebase ID token |

### 5.1. Những trường cần xác minh của Firebase ID token

Firebase Admin SDK kiểm tra signature, expiration, issuer/audience gắn với **Firebase project** và cấu trúc token theo SDK. Java nên sử dụng `FirebaseAuth.verifyIdToken(idToken)` thay vì chỉ giải mã JWT bằng Base64.

Khi cần kiểm tra thu hồi/disabled account, gọi `verifyIdToken(idToken, true)`; thao tác này phát sinh thêm network request đến Firebase Auth và làm tăng latency/cost vận hành. Không bật hay tắt một cách tuỳ tiện: chọn theo risk profile và khả năng phục hồi của hệ thống.

Với request có quyền cao, có thể kiểm tra **`auth_time`** để yêu cầu đăng nhập lại gần đây (recent sign-in), ngoài check token expiry/revocation.

### 5.2. Cookie đăng nhập cho server-rendered web

Nếu Java server dùng session cookie:

1. Client đăng nhập qua Firebase SDK rồi gửi ID token tới endpoint `/sessionLogin` qua HTTPS.
2. Server **xác minh ID token** và yêu cầu **CSRF token** hợp lệ, sau đó dùng Admin SDK tạo session cookie.
3. Trả cookie với `HttpOnly`, `Secure`, `SameSite` phù hợp; giới hạn path/domain và TTL.
4. Mỗi request server cần `verifySessionCookie`; tuỳ yêu cầu có thể check revoked.
5. Logout phải huỷ cookie/session, cân nhắc `revokeRefreshTokens(uid)` khi muốn thu hồi rộng.

**Firebase session cookie không dùng thay ID token để gọi trực tiếp Firestore/Firebase client SDK.** Nó dành cho server-side session management; server phải enforce authorization riêng.

## 6. Thực hành A — Web SDK đăng nhập và gọi Java API

**Điều kiện:** sandbox Firebase project, đã đăng ký Web app, bật **Email/Password** provider và cấu hình authorized domains; không dùng email hay mật khẩu production trong lab. Có HTTPS Java API `https://JAVA_API_HOST` đang hoạt động theo mô hình truy cập được phép.

### 6.1. Bật provider trong console

Trong Firebase Console → **Authentication → Sign-in method**, bật **Email/Password** cho project lab. Xác định chính xác **project ID, auth domain và API key của web app** từ Firebase project settings.

**API key của Firebase Web SDK không phải mật khẩu service account**; nó định danh Firebase project/app khi gọi một số Firebase APIs. Dù không phải secret bảo vệ dữ liệu, vẫn cần **API key restrictions** khi khả thi, anti-abuse measures, Security Rules và không nhầm key với quyền người dùng.

### 6.2. JavaScript modular Web SDK

Mẫu minh hoạ cho ứng dụng web đã cài package `firebase` và thực hiện đăng nhập bằng email/mật khẩu:

~~~javascript
import { initializeApp } from "firebase/app";
import {
  getAuth, signInWithEmailAndPassword,
  signOut
} from "firebase/auth";

const app = initializeApp({
  apiKey: "FIREBASE_WEB_API_KEY",
  authDomain: "PROJECT_ID.firebaseapp.com",
  projectId: "PROJECT_ID",
  appId: "FIREBASE_APP_ID"
});

const auth = getAuth(app);

export async function signInAndCallApi(email, password) {
  const userCredential =
    await signInWithEmailAndPassword(auth, email, password);

  // Không log token hoặc đưa token vào URL/query string.
  const idToken = await userCredential.user.getIdToken();

  const response = await fetch("https://JAVA_API_HOST/api/me", {
    method: "GET",
    headers: { Authorization: "Bearer " + idToken }
  });

  if (!response.ok) {
    throw new Error("API request failed: " + response.status);
  }

  return await response.json();
}

export async function logout() {
  await signOut(auth);
}
~~~

**Điểm cần hiểu:**

- Client SDK tự quản lý refresh token và có thể cấp ID token mới khi cần; không lưu raw token trong local storage thủ công nếu không có lý do.
- `userCredential.user.uid` giúp hiển thị UI, nhưng server **không tin UID lấy từ JSON body hoặc header tự khai**. Java phải suy danh tính từ **Firebase ID token đã verify**.
- Cần HTTPS, cấu hình CORS nếu frontend/backend khác origin; **CORS không phải authorization**.
- Nếu API Cloud Run có IAM yêu cầu **Google Cloud Invoker token**, Firebase ID token **không phải** token Cloud Run IAM. Chọn trust boundary: public/authentication tại Java ingress với Firebase token, hoặc có gateway/proxy phù hợp; không mở data access trong Java.

### 6.3. Trường hợp không nên dùng email/password trực tiếp

Nếu doanh nghiệp yêu cầu SSO Microsoft Entra ID/SAML hoặc OIDC tuỳ chỉnh, dùng **Identity Platform provider federation** thay vì yêu cầu nhân viên lập thêm mật khẩu Firebase. Điều này cần cấu hình issuer/certificate/redirect và xử lý account linking; không thể chỉ đổi tên provider trong Web SDK mà bỏ bước setup.

## 7. Thực hành B — Java Cloud Run xác minh Firebase ID token

**Kiến trúc:** Java Spring Boot (JDK 17 trở lên) nhận `Authorization: Bearer FIREBASE_ID_TOKEN`; Firebase Admin SDK xác minh token, sau đó application kiểm tra user/role và mới truy cập Firestore hoặc Cloud SQL.

### 7.1. Maven dependency cho Admin SDK

Trong Spring Boot Maven project đã có `spring-boot-starter-web`, thêm:

~~~xml
<dependency>
  <groupId>com.google.firebase</groupId>
  <artifactId>firebase-admin</artifactId>
  <version>9.12.0</version>
</dependency>
~~~

`9.12.0` là một phiên bản Admin Java SDK phát hành ngày **11/11/2026** (dùng làm ví dụ pin version). Luôn kiểm tra release notes, tương thích Java/Spring dependencies và security advisories khi nâng cấp. Không chèn JSON key vào `pom.xml` hoặc source code.

### 7.2. Khởi tạo Firebase Admin SDK bằng ADC

Tạo class `FirebaseAdminConfig.java` (đặt trong package được Spring Boot quét):

~~~java
package com.example.orders;

import com.google.auth.oauth2.GoogleCredentials;
import com.google.firebase.FirebaseApp;
import com.google.firebase.FirebaseOptions;
import com.google.firebase.auth.FirebaseAuth;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class FirebaseAdminConfig {
    @Bean
    public FirebaseApp firebaseApp() throws Exception {
        String projectId = System.getenv("FIREBASE_PROJECT_ID");
        if (projectId == null || projectId.isBlank()) {
            throw new IllegalStateException("FIREBASE_PROJECT_ID is required");
        }
        FirebaseOptions options = FirebaseOptions.builder()
            .setCredentials(GoogleCredentials.getApplicationDefault())
            .setProjectId(projectId)
            .build();
        return FirebaseApp.initializeApp(options);
    }

    @Bean
    public FirebaseAuth firebaseAuth(FirebaseApp app) {
        return FirebaseAuth.getInstance(app);
    }
}
~~~

Trên Cloud Run/GKE/Compute Engine, dùng **runtime service account** và ADC; cấp IAM tối thiểu cho thao tác Admin SDK cụ thể. Ví dụ service chỉ **verify local JWT** không nên có role Identity Platform Admin toàn project. Khi gọi user lookup, revoke refresh tokens, set claims hoặc tạo custom tokens mới cần quyền tương ứng. **Không** cấp `roles/owner` hoặc `roles/identitytoolkit.admin` cho mọi API service một cách mặc định.

**Local testing nuance:** credential người dùng cuối từ `gcloud auth application-default login` mặc định có thể **không được Firebase Authentication Admin SDK chấp nhận cho một số auth operations**. Khi thử local cần project ID và OAuth client/ADC phù hợp theo tài liệu; tốt hơn dùng **Firebase Authentication Emulator Suite** hoặc môi trường test với workload identity. Tránh tải JSON key lâu hạn chỉ để thử demo.

### 7.3. REST controller xác minh user token

Tạo class `MeController.java` trong cùng package; Java backend sẽ trả `401` nếu thiếu/sai token, `403` nếu yêu cầu nghiệp vụ bị từ chối:

~~~java
package com.example.orders;

import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.auth.FirebaseAuthException;
import com.google.firebase.auth.FirebaseToken;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {
    private final FirebaseAuth firebaseAuth;

    public MeController(FirebaseAuth firebaseAuth) {
        this.firebaseAuth = firebaseAuth;
    }

    @GetMapping("/api/me")
    public ResponseEntity<?> me(
        @RequestHeader(value = "Authorization", required = false)
        String authorization
    ) {
        if (authorization == null || !authorization.startsWith("Bearer ")) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body(Map.of("error", "missing_bearer_token"));
        }

        String idToken = authorization.substring("Bearer ".length()).trim();
        if (idToken.isEmpty()) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body(Map.of("error", "invalid_token"));
        }

        try {
            // true: kiểm tra token revoked/disabled, thêm network request.
            FirebaseToken verified =
                firebaseAuth.verifyIdToken(idToken, true);

            String uid = verified.getUid();
            // Đối với endpoint này chỉ trả UID; các route nghiệp vụ
            // phải kiểm tra quyền trên order/tenant trước khi query DB.
            return ResponseEntity.ok(Map.of("uid", uid));
        } catch (FirebaseAuthException e) {
            // Không đưa ID token hoặc thông tin lỗi nhạy cảm ra response.
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body(Map.of("error", "invalid_or_revoked_token"));
        }
    }
}
~~~

**Giới hạn minh hoạ:** Đây là controller + bean hoàn chỉnh cho **project Spring Boot Web đã có entrypoint**, không phải toàn bộ ứng dụng dựng từ một file. `/api/me` chỉ xác nhận user identity. Với `GET /api/orders/{id}`, phải kiểm tra `ownerUid`/`tenantId` trong business layer và trả **403** nếu caller đã xác thực nhưng không có quyền. Nếu có Java API routes khác, nên dùng **Spring Security filter** áp authentication nhất quán thay vì copy controller logic từng nơi.

### 7.4. Khi nào cần check revocation?

| Ngữ cảnh | Khuyến nghị |
|---|---|
| Trang hồ sơ đơn giản, tải cao | Cân nhắc `verifyIdToken(token)` và chính sách token TTL/authorization, cân bằng độ trễ |
| Truy cập billing, dữ liệu nhạy cảm, admin | `verifyIdToken(token, true)` khi cần cưỡng chế thu hồi sớm |
| Quyền quản trị vừa bị giảm | Phải hiểu **ID token cũ chứa claims cũ**; dùng refresh/check nguồn quyền bền vững hoặc revoke sessions |
| Account bị khoá hoặc nghi token bị đánh cắp | Revoke refresh tokens, check revoked/disabled và điều tra sessions |

**Chỉ kiểm tra chữ ký JWT không tự biết refresh token đã bị revoke.** Firebase ID token thường tồn tại đến hết hạn; vì vậy phải đặt rõ yêu cầu về **thời gian hiệu lực của thay đổi quyền**.

## 8. Security Rules + Java authorization

### 8.1. Firestore Rules cho user-owned documents

Mẫu client-side rule trong Firestore Native:

~~~javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{userId} {
      allow read: if request.auth != null
                  && request.auth.uid == userId;
      allow write: if false;
    }

    match /orders/{orderId} {
      allow read: if request.auth != null
                  && resource.data.ownerUid == request.auth.uid;
      allow write: if false;
    }
  }
}
~~~

Điều này cho phép mobile/web Firebase SDK đọc profile/order thuộc user đã xác thực; dữ liệu được tạo/sửa bởi **backend Java** dùng IAM. Một truy vấn lấy **tất cả** orders rồi mong Rules tự lọc order của user **có thể bị từ chối**: **Security Rules không phải bộ lọc**. Query của client phải ràng buộc `ownerUid == request.auth.uid`; xây index phù hợp.

### 8.2. Java server không được “bỏ qua Rules” theo nghĩa bỏ qua bảo mật

Java server Admin/Firestore SDK **bypass Rules** vì dùng Google IAM. Server phải:

1. Xác thực HTTP caller bằng Firebase ID token.
2. Xác định `uid` và, nếu có, `tenantId` từ **token đã verify**.
3. Tra cứu order, đối chiếu `ownerUid`/`tenantId` với quyền nghiệp vụ.
4. Chặn request `403` nếu caller không có quyền; không chỉ xem client đã logged in.
5. Chỉ thực thi query/transaction cho đúng dữ liệu được cho phép.
6. Ghi audit không chứa raw token, PII hoặc database secret.

Không lấy `request.queryParams.uid` hay `X-Tenant-Id` do client tự cung cấp làm principal. Nếu cần chọn tenant theo URL, phải đối chiếu với **tenant trong token** và membership/entitlements tại backend.

### 8.3. Identity Platform và App Check có bổ trợ gì?

**Firebase App Check** dùng app/device attestation để giảm một số kiểu request giả mạo từ app không hợp lệ. App Check **không xác thực người dùng**, còn Authentication **không chứng minh request đến từ một app build hợp lệ**. Với custom Java backend, cần **gửi và verify App Check token riêng** nếu áp dụng; đừng nhận một header tuỳ ý rồi coi đã có App Check.

## 9. Custom claims và quản lý quyền trong Identity

Custom claims giúp lưu **vai trò nhỏ** như `admin`, `support` hoặc một quyền chung vào Firebase ID token.

~~~java
import com.google.firebase.auth.FirebaseAuth;
import java.util.Map;

// Đoạn này CHỈ chạy ở môi trường admin được ủy quyền.
String uid = "TEST_UID";
FirebaseAuth.getInstance().setCustomUserClaims(
    uid, Map.of("support", true));
~~~

Firebase custom claims:

- Chỉ **trusted server/Admin SDK** được cấp quyền đặt claims; không lấy `isAdmin` do client tự gửi.
- Payload claims giới hạn khoảng **1.000 bytes**; không dùng lưu profile, danh sách hàng nghìn tenants hoặc PII.
- Claims mới xuất hiện khi **ID token refresh** hoặc user đăng nhập lại; không tác động ngược mọi token đang còn hiệu lực.
- `setCustomUserClaims` có semantics **thay thế bộ claims** đã lưu, nên cần merge từ nguồn tin cậy khi có nhiều quyền; không vô tình xóa các claims khác.
- **Custom token claims** có thể ảnh hưởng token sau sign-in theo precedence được tài liệu quy định; không sử dụng custom token để “cho user tự chọn vai trò”.

### 9.1. Kết hợp claims và policy trong Java

~~~java
FirebaseToken token = firebaseAuth.verifyIdToken(idToken, true);
boolean support = Boolean.TRUE.equals(token.getClaims().get("support"));
if (!support) {
    // Trả HTTP 403; không dùng claim chưa được verify.
}
~~~

**Claims trong token không phải database role engine.** Việc user có `support=true` không tự cấp Google IAM Firestore `roles/datastore.user`. Đối với quyền thay đổi liên tục hoặc theo mỗi order, query **authorization datastore** của ứng dụng vẫn quan trọng.

### 9.2. Admin User Management API

Firebase Admin SDK có thể tạo/cập nhật/disable/delete users và revoke refresh tokens:

~~~java
import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.auth.UserRecord;

// Chỉ thực thi trong tool/admin workflow đã cấp quyền.
UserRecord user = FirebaseAuth.getInstance().getUser("TEST_UID");
FirebaseAuth.getInstance().updateUser(
    new UserRecord.UpdateRequest(user.getUid()).setDisabled(true));
FirebaseAuth.getInstance().revokeRefreshTokens(user.getUid());
~~~

**Không thực thi trực tiếp đoạn trên với UID thật trong production** khi không có kế hoạch phê duyệt. Disable/revoke **không đồng nghĩa mọi ID token cũ lập tức vô hiệu nếu backend không kiểm tra revocation/disabled**. Offboarding phải xem cả active sessions, custom claims, linked providers, dữ liệu cá nhân và retention/compliance.

## 10. Identity Platform: multi-tenancy cho SaaS và B2B

### 10.1. Tenant là gì?

Với Identity Platform, **tenant** là user pool và tập cấu hình identity riêng trong cùng Google Cloud/Firebase project: provider, user accounts, policy phù hợp. Các tenants có IDs riêng; một email có thể xuất hiện ở nhiều tenants như **các tài khoản identity khác nhau**.

~~~mermaid
flowchart LR
    WebA["Portal khách hàng A"] --> A["Identity tenant A<br/>OIDC IdP A"]
    WebB["Portal khách hàng B"] --> B["Identity tenant B<br/>SAML IdP B"]
    A --> API["Java multi-tenant API"]
    B --> API
    API --> Guard["Verify tenant-aware token<br/>+ tenant authorization"]
    Guard --> Data["Orders phân vùng tenant"]
~~~

**Tenant identity không tự chia tách Firestore, Cloud SQL hay Storage dữ liệu**. Nếu dùng chung backend/database, Java phải kiểm tra `tenantId` trên token, đối chiếu business membership và enforce mọi query theo tenant. Với yêu cầu cách ly mạnh, cân nhắc project/database/service isolation bổ sung.

### 10.2. Client xác định tenant trước sign-in

Với Firebase Web SDK đã cấu hình:

~~~javascript
import { getAuth, signInWithEmailAndPassword } from "firebase/auth";

const auth = getAuth();
auth.tenantId = "TENANT_A_ID";

const credential = await signInWithEmailAndPassword(
  auth, "user@tenant-a.example", "TEST_PASSWORD");
const idToken = await credential.user.getIdToken();
~~~

`tenantId` không tự được lưu bền vững qua mọi page reload; sau reload phải xác định và set lại tenant phù hợp trước auth operation. **Không tin tenant ID chỉ từ subdomain/URL** nếu user có thể mạo danh; server phải kiểm tra tenant trong ID token.

### 10.3. Java dùng TenantAwareFirebaseAuth

~~~java
import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.auth.FirebaseToken;
import com.google.firebase.auth.TenantAwareFirebaseAuth;

String tokenFromClient = "VERIFIED_TRANSPORT_ONLY";
String expectedTenant = "TENANT_A_ID";

TenantAwareFirebaseAuth tenantAuth =
    FirebaseAuth.getInstance()
        .getTenantManager()
        .getAuthForTenant(expectedTenant);

FirebaseToken verified = tenantAuth.verifyIdToken(tokenFromClient, true);
// Tenant khác expectedTenant → xác minh thất bại.
String uid = verified.getUid();
String tenantId = verified.getTenantId();
~~~

**Nếu Java phục vụ nhiều tenants và không biết trước tenant nào**, có thể xác minh token ở cấp project để lấy tenant ID, **sau đó** dùng tenant-aware auth tương ứng để kiểm tra revoked status. **Không gọi project-level `verifyIdToken(token, true)` trên tenant user rồi suy user bị xóa**, vì revocation check project-level áp user pool gốc và có thể báo `user-not-found` cho tenant-specific users. Phải whitelist tenant và enforce tenant→resource relationship.

## 11. SAML, OIDC, MFA và blocking functions

### 11.1. Enterprise federation (SAML/OIDC)

Identity Platform hỗ trợ cấu hình IdP theo SAML/OIDC, trong phạm vi hỗ trợ:

| Công việc | Những gì phải kiểm tra |
|---|---|
| OIDC | Issuer URL, client ID/secret, redirect URI, signing keys, scopes, email claims |
| SAML | Entity ID, SSO URL, X.509 signing certificate, NameID mapping, assertion time |
| Account linking | Không tự gộp hai users khác UID/email mà không xác minh quyền sở hữu |
| Tenant-specific IdP | Cấu hình provider đúng tenant thay vì project global |
| JIT provisioning | User lifecycle, group/role mapping, deletion/offboarding |
| Security | PKCE/state/nonce theo SDK/provider flow và tránh open redirects |

**Đừng tự triển khai SAML signature validation thủ công trong Java API** khi Identity Platform có thể xử lý federation. Java chỉ nên tiêu thụ Firebase ID token đã verify và kiểm tra quyền nghiệp vụ.

### 11.2. MFA: SMS hoặc TOTP

Identity Platform hỗ trợ **multi-factor authentication** với SMS hoặc TOTP trong cấu hình được hỗ trợ.

- **TOTP** dùng authenticator app; không cần gửi SMS nhưng cần quy trình enrollment, recovery và bảo vệ secret.
- **SMS MFA** có chi phí tin nhắn, quota, rủi ro SIM swap và vùng hỗ trợ.
- MFA có điều kiện về **provider đăng nhập đầu tiên và email verification**; một số nguồn như **anonymous, phone, custom-token sign-in** không được dùng làm first factor theo hướng dẫn TOTP.
- Enforce MFA cho tài khoản nhạy cảm, nhóm admin hoặc hành động rủi ro cao; thiết kế recovery không làm yếu bảo mật.

**MFA không tự xác thực authorization của mỗi order** và không thay security rules.

### 11.3. Blocking functions: chặn trước khi tạo user/đăng nhập

Có thể dùng `beforeUserCreated` và `beforeUserSignedIn` để kiểm tra domain email, risk policy hoặc enrich claims **trước khi Firebase Auth cấp ID token**. Đặc tính vận hành quan trọng:

- Blocking functions có **deadline ngắn (7 giây theo tài liệu hiện hành)**, lỗi/timeout có thể chặn cả đăng ký hoặc đăng nhập.
- User creation có thể chạy cả create và sign-in hooks.
- **Anonymous và custom auth** không kích hoạt blocking functions theo quy định hiện hành.
- Nếu xoá function nhưng **không unregister trigger**, người dùng có thể không đăng nhập được.
- Với multi-tenancy, function có thể ảnh hưởng nhiều tenants; kiểm tra scope, feature flags và circuit-breaker/fallback policy.

**Không đặt nghiệp vụ mất nhiều giây hoặc phụ thuộc API bất ổn vào blocking function.** Nó nằm trên đường đăng nhập của mọi người dùng; cần SLO, monitoring và rollback riêng.

## 12. Bảo mật tài khoản, token và luồng HTTP

### 12.1. Kiểm soát thiết yếu

1. **HTTPS** mọi kết nối gửi ID token; không đưa token vào URL/query string, logs hoặc analytics.
2. Chọn phương thức lưu phiên phù hợp platform; web tránh xử lý refresh token thủ công.
3. Bật email verification, password policy, anti-abuse/rate limiting và cảnh báo sign-in bất thường.
4. Thực thi account linking thận trọng, không gộp theo email chưa verified.
5. Các API nhạy cảm cần **recent authentication**, revocation check và authorization trên từng resource.
6. Với session cookie, đặt `Secure`, `HttpOnly`, `SameSite`, CSRF token và thời hạn phù hợp.
7. **App Check** bảo vệ tính hợp lệ app/device, là lớp bổ sung — không thay Firebase Authentication.
8. Hạn chế IAM của backend/admin tooling: role `roles/identitytoolkit.admin` hoặc `roles/identityplatform.admin` chỉ dành cho nhiệm vụ quản trị cần thiết.
9. Tách **test/staging/prod projects**, token audience/project và quy trình rotate provider credentials.
10. Xác định data retention, export/deletion và yêu cầu pháp lý đối với dữ liệu người dùng.

### 12.2. Firebase Auth ID token khác Google Cloud Run IAM token

| Mục đích | Token đúng |
|---|---|
| Web user gọi Java API do ứng dụng tự xác thực Firebase | **Firebase ID token** |
| Cloud Scheduler gọi private Cloud Run IAM-protected service | **Google-signed OIDC ID token** của service account có `roles/run.invoker` |
| Java server gọi Google Cloud API | **ADC/OAuth access token** của runtime service account |
| Mobile client truy cập Firestore Native | Firebase Auth session/Rules, và App Check nếu bật |
| Java server truy cập Firestore Native | Google IAM của runtime SA, **không phải Firebase UID token** |

**Một Firebase ID token hợp lệ không tự vượt qua Cloud Run Invoker IAM.** Nếu Cloud Run đang yêu cầu IAM identity ở ingress, cần một frontend/gateway hoặc mô hình access phù hợp; hoặc cấu hình endpoint có thể nhận HTTP request rồi **Java tự xác thực Firebase**, kết hợp Cloud Armor/rate limiting và security controls cần thiết. Không được coi `--allow-unauthenticated` là “cho phép dữ liệu công khai”; quyền ứng dụng còn phải enforce trong code.

## 13. Thực hành C — Kiểm thử và quy trình quản trị

### 13.1. Test Firebase client + Java end-to-end

Chuẩn bị riêng **Firebase Auth test project** và **Java API sandbox**. Bộ test nên gồm:

| Trường hợp | Kỳ vọng |
|---|---|
| Đăng nhập đúng rồi gọi `/api/me` với ID token hợp lệ | HTTP 200, trả UID đã verify |
| Bỏ Authorization header | HTTP 401 |
| Dùng token bị sửa một byte | HTTP 401 |
| Dùng token từ **Firebase project khác** | HTTP 401 |
| Dùng token cũ/hết hạn | HTTP 401 |
| Disable/revoke user, gọi API có checkRevoked | HTTP 401 |
| Token user A đọc order của B | HTTP 403 |
| Firebase mobile query docs ngoài scope Rules | `PERMISSION_DENIED` |
| Java runtime SA thiếu Firestore IAM permission | Cloud client API `PERMISSION_DENIED` ở server |
| Multi-tenant token A dùng API tenant B | HTTP 401 hoặc 403, tùy policy xác thực/ủy quyền |

Đối với unit/integration tests, **Firebase Authentication Emulator Suite** có thể giúp tạo user/tokens ở môi trường thử; cần cấu hình endpoint emulator tách biệt. **Emulator-issued tokens không bảo đảm chữ ký production như token thật**, nên tuyệt đối không trỏ production Admin SDK sang emulator hoặc tin tưởng unsigned emulator tokens trong production.

### 13.2. Xem các cấu hình theo cách an toàn

- Firebase Console → Authentication → Providers / Users / Settings: kiểm tra provider được bật và authorized domains.
- Google Cloud Console → Identity Platform → Providers / Tenants: kiểm tra federation, tenant policies và cấu hình upgrade nếu áp dụng.
- Cloud IAM: xác minh **principal đang chạy Java** và các role cần thiết; không tiết lộ private credentials.
- Firebase/Identity Platform Logs: hoạt động đăng nhập và lỗi nhà cung cấp; phân biệt **Cloud Audit Logs** cho admin changes và **Activity logging** cho user sign-in.

**Activity logging của Identity Platform mặc định tắt theo tài liệu**, cần chủ động bật nếu chính sách bảo mật và privacy cho phép; lưu trữ logs có thể tạo chi phí và phải tránh thu thập dữ liệu nhạy cảm không cần thiết.

### 13.3. Chạy thử thay đổi quyền

Khi muốn thu hồi quyền `support`:

1. Đổi quyền trong **nguồn dữ liệu tin cậy**; cập nhật custom claims trên user bằng Admin SDK.
2. Nếu cần thay đổi có hiệu lực sớm, revoke refresh tokens và yêu cầu client reauthenticate.
3. Java API có revocation check và/hoặc query permission state bền vững khi xử lý route nhạy cảm.
4. Thử session cũ, mới, các thiết bị khác, cookies và tenant-specific users.
5. Ghi bằng chứng rằng user không còn đọc được dữ liệu vượt quyền.

Không test bằng cách cấp quyền quản trị cho client rồi thử xoá users trong project thực.

## 14. Chi phí, quota, SLA và vận hành

### 14.1. Tính phí theo loại provider và mức sử dụng

Identity Platform thường tính tiền dựa trên **MAU (Monthly Active Users)**:

| Loại | Cách tính cần kiểm tra |
|---|---|
| Email/social/anonymous/custom | Theo MAU, có **no-cost tier 50.000 MAU** trên gói phù hợp |
| **SAML / generic OIDC** | Nhóm giá riêng, no-cost tier nhỏ hơn (ví dụ **50 MAU**) |
| SMS phone sign-in / SMS MFA | **Tính phí theo tin nhắn**, vùng nhận và giới hạn |
| Firebase Auth with Identity Platform không có billing instrument | Có thể bị giới hạn **daily active users** |
| Blocking functions/Cloud Run/Cloud Functions | Ngoài MAU còn compute/network/logging |
| Cloud Logging/Monitoring và App Check | Phí/quota theo dịch vụ và nhà cung cấp attestation |

**Không đo chi phí bằng tổng số tài khoản được lưu.** Một user chưa đăng nhập trong tháng có thể không được tính MAU; **monthly active** khác **registered users**. Với số điện thoại, phí SMS và chống fraud có thể quan trọng hơn giá MAU. Giá và ngưỡng có thể thay đổi; xem pricing pages và Billing Reports tại thời điểm triển khai.

Theo tài liệu Firebase Authentication with Identity Platform, **Spark plan không gắn billing instrument** có giới hạn **3.000 DAU tier 1 và 2 DAU tier 2** (khác với ngưỡng MAU của Blaze). Đừng lấy **50.000 MAU** suy ra mọi project Spark có thể phục vụ 50.000 daily sign-ins mà không bị giới hạn.

### 14.2. Quota và an toàn khi scale

- Rate limits cho **sign-ups, token exchanges, account lookups, password reset emails và SMS sends** có thể áp theo project/IP/provider.
- Email/SMS OTP là điểm dễ bị lạm dụng; cần App Check/reCAPTCHA và abuse controls được hỗ trợ.
- Multi-tenancy/enterprise federation thêm độ phụ thuộc tới external IdP và latency SSO.
- Blocking functions nằm trên critical path của login, phải đo failure rate và p95/p99.
- Check revocation cho mọi request làm tăng cuộc gọi đến Auth backend; cân nhắc cache, TTL và mức độ rủi ro.
- SLO thật cần đo **successful sign-in + API usable + resource access đúng quyền**, không chỉ xác thực provider.

## 15. Troubleshooting: tách lỗi identity khỏi lỗi dữ liệu

| Triệu chứng | Nguyên nhân khả dĩ | Chẩn đoán |
|---|---|---|
| Web sign-in `auth/invalid-credential` | Sai credential/provider hoặc tài khoản không hợp lệ | Provider enablement, test user, client error code |
| `auth/unauthorized-domain` | Domain web chưa được phép | Firebase Auth authorized domains |
| Google/OIDC redirect thất bại | URI, issuer, OAuth consent, state/nonce | Provider configuration và callback logs |
| Firebase ID token gửi Java bị 401 | Thiếu Bearer, token hết hạn, sai signature/project | Backend `verifyIdToken`, project ID |
| Token valid nhưng Java trả 403 | Tenant/role hoặc ownerUid của order không đúng | Domain authorization, claims và dữ liệu |
| Cloud Run ingress trả 401/403 **trước khi vào Java** | IAM Invoker thiếu hoặc Firebase token không phải Cloud Run IAM token | Cloud Run ingress policy và request logs |
| Java Admin SDK thiếu permission | Runtime SA IAM không đủ cho user management | IAM role/permission cần cho thao tác |
| Token vừa revoke vẫn được chấp nhận | Không check revoked hoặc token chưa hết hạn | `verifyIdToken(token, true)` và session policy |
| Custom claim mới không thấy | ID token chưa refresh, claims bị overwrite | Force refresh/new sign-in, Admin `getUser` |
| Multi-tenant user báo `user-not-found` | Revocation check project-level thay tenant-level | TenantAwareFirebaseAuth |
| Firebase Rules deny query đọc nhiều orders | Rules không phải filters, query thiếu ownerUid | Query constraints và Rules tests |
| Java Firestore server vẫn đọc dù Rules deny | Admin/server SDK bypass Rules | Cloud IAM/runtime SA và app authorization |
| MFA TOTP enrollment không hoạt động | First-factor/provider/email verification chưa hợp lệ | Identity Platform MFA settings |
| Blocking function chặn mọi login | Function timeout/error hoặc bị xoá không unregister | Auth trigger config, function logs/rollbacks |
| SMS tăng chi phí | OTP fraud/retry, phone sign-in traffic | Identity Platform usage, rate limits, Billing |
| Local Java Admin SDK ADC lỗi | ADC user OAuth client không được chấp nhận, sai project | SDK setup và Emulator configuration |

### 15.1. Runbook sáu bước

1. **Ai đang gọi?** Web/mobile user, Java runtime SA hay CI deployer?
2. **Thất bại ở đâu?** Provider sign-in, Firebase ID token, Cloud Run ingress, Java authorization, Firestore Rules hay IAM?
3. **Dự án/tenant nào?** So project ID, issuer/audience, tenant ID, client SDK configuration.
4. **Token nào?** Firebase ID token, custom token, Google OIDC IAM token hay App Check token.
5. **Quyền nào?** User claims/tenant/order ownership, Rules hay IAM của runtime SA.
6. **Khắc phục có kiểm soát:** thử trên sandbox, xem logs/metrics và test negative cases trước khi production.

Không sửa 403 bằng `allow read, write: if true`, tắt Java authorization, cấp Owner hoặc in raw token lên log.

## 16. Case study — RetailOne Java Orders API và đối tác B2B

**Bối cảnh:** RetailOne có ứng dụng mobile theo dõi đơn hàng và **Java Orders API** chạy Cloud Run, dữ liệu orders ở Firestore Native. Ban đầu chỉ đăng nhập Google/email; sau đó hai đối tác doanh nghiệp muốn dùng SAML và mỗi đối tác có user pool riêng.

### 16.1. Thiết kế theo giai đoạn

| Giai đoạn | Giải pháp |
|---|---|
| **A. Mobile consumer** | Firebase Authentication cơ bản, Firebase SDK, Rules `ownerUid == auth.uid` |
| **B. Java Orders API** | Firebase Admin Java verify ID token, domain authorization, runtime SA + Firestore IAM |
| **C. Enterprise SSO** | Nâng cấp Firebase Auth with Identity Platform, cấu hình SAML/OIDC provider |
| **D. B2B multi-tenant** | Identity Platform tenants, tenant-aware token verification, dataset separation policy |
| **E. Bảo mật cao hơn** | MFA, revocation handling, blocking functions có SLO và App Check |

### 16.2. Vì sao phân tách identity là quan trọng?

~~~mermaid
flowchart LR
    A["Mobile user A"] --> Auth["Firebase Auth"]
    B["Partner B employee"] --> Tenant["Identity Platform tenant B"]
    Auth --> Java["Cloud Run Java Orders API"]
    Tenant --> Java
    Java --> Guard["Verify token + tenant + owner + role"]
    Guard --> IAM["Runtime service account + Firestore IAM"]
    IAM --> Docs["Firestore orders"]
~~~

Một kỹ sư có thể vô tình viết endpoint `GET /api/orders/{id}` chỉ kiểm tra “token hợp lệ”. Khi đối tác B biết `orderId` của tenant A, backend đang có IAM read toàn collection nên có thể trả dữ liệu trái phép.

**Sửa đúng:** sau verify, Java dùng `tenantId`/`uid` từ token, đọc metadata đơn hàng, kiểm tra `ownerUid` và `tenantId` theo policy rồi mới trả response. **Không dùng claim email/domain làm duy nhất bằng chứng tenant**, vì email/IdP mapping có thể thay đổi.

### 16.3. Kế hoạch triển khai và rollback

1. Kiểm kê providers, lượng MAU, SLA, session lifecycle, Rules và IAM.
2. Ước tính phí MAU/SAML/SMS/Cloud Functions trước khi nâng Identity Platform.
3. Tạo/test tenant SAML trong môi trường staging; kiểm tra login failure/redirect/MFA.
4. Thử backend Java với tenant A/B, token sai project và token hết hạn.
5. Chạy Security Rules emulator để đảm bảo user A không đọc order B.
6. Mở feature flag cho nhóm pilot; quan sát sign-in error rate, 401/403 và SLO.
7. Có playbook thu hồi tenant provider/claims và xử lý session khi sự cố; không giả định upgrade cấp sản phẩm có thể rollback đơn giản bằng một nút.
8. Audit chi phí, IAM roles và trải nghiệm đăng nhập định kỳ.

## 17. Bài tập và tự đánh giá

### Bài 1 — Nhận diện hệ thống identity

User đăng nhập Firebase bằng Google, sau đó Java Cloud Run đọc Firestore qua service account.

**Hỏi:** Firebase `uid`, Cloud Run runtime SA và deployer IAM principal là các danh tính nào? Ai quyết định user có quyền xem order?

**Gợi ý:** backend domain authorization kiểm tra owner/tenant; Firebase UID không là GCP IAM service account.

### Bài 2 — Chọn Firebase Auth hay Identity Platform

Ứng dụng mobile 2.000 users, chỉ có email/Google sign-in. Một sản phẩm B2B khác cần SAML và mỗi doanh nghiệp có IdP riêng.

**Hỏi:** giải pháp nào cho mỗi sản phẩm và vì sao? Điều gì đổi về billing khi upgrade?

### Bài 3 — Firebase ID token vs custom token

Java backend tạo `createCustomToken(uid)` rồi client gửi thẳng token đó vào `/api/orders`. Java gọi `verifyIdToken` và nhận lỗi.

**Hỏi:** thiếu bước nào?

**Gợi ý:** client cần `signInWithCustomToken` để đổi lấy **Firebase ID token**.

### Bài 4 — Firebase Auth vs Cloud Run Invoker

Web SDK gửi Firebase ID token nhưng Cloud Run trả 403 trước khi code Java chạy.

**Hỏi:** vì sao valid Firebase token chưa đủ? Thiết kế ingress thế nào?

### Bài 5 — Security Rules không ngăn Java

Firestore Rules deny-all, nhưng Java Admin SDK trên Cloud Run vẫn đọc được `orders`.

**Hỏi:** lỗi ở đâu? Cần kiểm soát IAM/runtime SA và Java business authorization thế nào?

### Bài 6 — Thu hồi quyền support

Người dùng bị xoá custom claim `support`, nhưng session cũ vẫn truy cập endpoint trong một thời gian.

**Hỏi:** cơ chế refresh, revocation và quyền bền vững nào giúp chính sách có hiệu lực đúng thời hạn?

### Bài 7 — Multi-tenant user pool

Tenant A và B đều có tài khoản `user@example.com`. Java nhận token tenant A nhưng URL yêu cầu `/tenant/B/orders`.

**Hỏi:** phải kiểm tra tenant ID ở đâu, ngoài email? Vì sao project-level revoked check có thể sai?

### Bài 8 — Blocking function thất bại

Identity Platform dùng `beforeUserSignedIn` gọi API rủi ro bên ngoài; API bị timeout 9 giây.

**Hỏi:** ảnh hưởng gì đến sign-in? Thiết kế độ tin cậy/rollback thế nào?

**Gợi ý:** blocking path có deadline khoảng 7 giây, cần short timeout/circuit-breaker và không phụ thuộc nặng.

### Bài 9 — MFA và App Check

Một nhóm đề xuất chỉ bật App Check để bảo vệ tài khoản admin, hoặc chỉ bật SMS MFA để chặn giả mạo app.

**Hỏi:** tại sao hai giải pháp có mục đích khác nhau? Nêu thiết kế phối hợp.

### Bài 10 — Chi phí và quota

Identity Platform có 70.000 MAU email/social, 400 MAU SAML/OIDC, 20.000 SMS mỗi tháng và nhiều blocking function invocations.

**Hỏi:** cần phân tách những SKU/quota nào khi dự toán? Có thể lấy free tier 50.000 MAU cho toàn bộ phương thức không?

### Bài 11 — Diễn tập bảo mật end-to-end

Hãy lập checklist kiểm thử cho ứng dụng RetailOne: user A, user B, tenant đối tác, ID token sai project, token revoke, custom claim stale, Firestore Rules, IAM server và API error codes. Nêu bằng chứng mong đợi trong logs mà **không lộ token hoặc PII**.

## 18. Checklist production

- [ ] Đã phân biệt Firebase Authentication cơ bản và các tính năng Identity Platform cần thiết.
- [ ] Provider đã bật theo nhu cầu, OAuth/SAML redirect và authorized domains đã kiểm tra.
- [ ] Email/password có verification, anti-abuse, password reset và account linking an toàn.
- [ ] ID token được gửi qua HTTPS bằng `Authorization: Bearer ...` và **verify bằng Admin SDK**.
- [ ] Java code không tin UID/tenant/role đến từ request chưa xác thực.
- [ ] Biết custom token cần exchange, ID token khác refresh token và Cloud Run IAM token.
- [ ] Có policy token expiry/revocation và recent sign-in cho thao tác nhạy cảm.
- [ ] Custom claims nhỏ, thuộc trusted admin workflow, không lưu PII/profile.
- [ ] Mobile/web Firestore Security Rules được test; biết Rules **không phải filters**.
- [ ] Java server Firestore SDK dùng IAM; có domain-level authorization và runtime SA tối thiểu.
- [ ] Cloud Run ingress được thiết kế rõ cho Firebase client hoặc service-to-service IAM.
- [ ] MFA/TOTP/SMS đã test provider eligibility, recovery và phí/quota.
- [ ] Multi-tenant token được verify bằng đúng tenant-aware client khi cần; dữ liệu tách bằng policy.
- [ ] Blocking functions có timeout, monitoring, fallback/rollback và tránh dependency dài.
- [ ] App Check được triển khai như **lớp bổ sung**, không thay user authentication.
- [ ] Session cookies có Secure/HttpOnly/SameSite/CSRF phù hợp nếu sử dụng.
- [ ] Auth Admin SDK dùng ADC/service identity; không commit service account JSON keys.
- [ ] IAM roles quản trị Identity Platform chỉ cấp cho operator cần thiết, được audit.
- [ ] Đã thử 401/403/revoked/expired/cross-project/cross-tenant và abuse cases.
- [ ] Activity logging/Audit Logs, quota, MAU/SMS và alerts được cấu hình theo privacy policy.
- [ ] Dự toán chi phí tier 1/tier 2 providers, SMS, compute blocking functions và logs.
- [ ] Có SLO đăng nhập và runbook khôi phục khi provider/SAML/IdP hay blocking function lỗi.

## 19. Tài liệu Firebase và Google Cloud chính thức

Đối chiếu APIs, IAM permissions, giá/quota, provider eligibility và yêu cầu vùng tại thời điểm triển khai:

- [Firebase Authentication — Tổng quan](https://firebase.google.com/docs/auth)
- [Identity Platform — Product comparison](https://docs.cloud.google.com/identity-platform/docs/product-comparison)
- [Identity Platform — Getting started](https://docs.cloud.google.com/identity-platform/docs/quickstart)
- [Firebase — Password authentication for web](https://firebase.google.com/docs/auth/web/password-auth)
- [Firebase — Admin SDK setup](https://firebase.google.com/docs/admin/setup)
- [Firebase — Verify ID tokens](https://firebase.google.com/docs/auth/admin/verify-id-tokens)
- [Firebase — Manage user sessions and revocation](https://firebase.google.com/docs/auth/admin/manage-sessions)
- [Firebase — Manage session cookies](https://firebase.google.com/docs/auth/admin/manage-cookies)
- [Firebase — Create custom tokens](https://firebase.google.com/docs/auth/admin/create-custom-tokens)
- [Firebase — Custom claims and Rules](https://firebase.google.com/docs/auth/admin/custom-claims)
- [Firebase — Admin user management](https://firebase.google.com/docs/auth/admin/manage-users)
- [Identity Platform — Multi-tenancy and tenant-aware Admin SDK](https://docs.cloud.google.com/identity-platform/docs/multi-tenancy-managing-tenants)
- [Firebase — Add TOTP MFA](https://firebase.google.com/docs/auth/web/totp-mfa)
- [Firebase — Blocking functions](https://firebase.google.com/docs/auth/extend-with-blocking-functions)
- [Firebase — Firestore Security Rules conditions](https://firebase.google.com/docs/firestore/security/rules-conditions)
- [Firebase — App Check](https://firebase.google.com/docs/app-check)
- [Identity Platform — Activity logging](https://docs.cloud.google.com/identity-platform/docs/activity-logging)
- [Identity Toolkit IAM roles](https://docs.cloud.google.com/iam/docs/roles-permissions/identitytoolkit)
- [Firebase Authentication usage limits](https://firebase.google.com/docs/auth/limits)
- [Identity Platform pricing](https://cloud.google.com/identity-platform/pricing)
- [Firebase Admin Java release notes](https://firebase.google.com/support/release-notes/admin/java)

**Điểm cần nhớ:** Firebase Authentication xác thực **người dùng cuối**, Identity Platform mở rộng thành **CIAM cho enterprise/SSO/multi-tenant**, còn **Google Cloud IAM** xác thực **backend service accounts**. Với Java Orders API, luồng đúng là **client sign-in → Firebase ID token → Admin SDK verify → kiểm tra tenant/owner/role → truy cập dữ liệu bằng runtime IAM**. Phân biệt **Security Rules, App Check, custom claims, session/revocation và Cloud Run Invoker**, kiểm thử negative cases và đánh giá MAU/SMS cùng SLO đăng nhập trước khi production.
