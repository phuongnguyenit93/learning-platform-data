# Firebase projects và quan hệ với Google Cloud projects

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao **Firebase project và Google Cloud project là cùng một project nền tảng**, không phải hai hệ thống độc lập cần đồng bộ thủ công.
2. Phân biệt **project display name, project ID, project number**, **Firebase App ID**, Android package name, Apple bundle ID và Web app registration.
3. Tạo Firebase project mới hoặc **thêm Firebase vào Google Cloud project hiện có** một cách có kiểm soát, không tạo nhầm project thứ hai.
4. Quản lý **IAM, Firebase Security Rules, service accounts, billing Spark/Blaze**, organization policies và Google Analytics đúng trách nhiệm.
5. Tách **development, staging, production**; cấu hình Firebase CLI, client app và Java/Cloud Run backend không lẫn project.
6. Kiểm tra sai project, permission denied, chi phí tăng và dữ liệu bị xóa bằng runbook có thể thực hành.

## 1. Bối cảnh: một hệ thống, hai bộ công cụ quản lý

Trong mô-đun **CLOUD_PROVIDERS_GCP**, bạn đã học **project, IAM, VPC, Cloud Run, GKE, Cloud Storage và database**. Firebase bổ sung các công cụ làm ứng dụng web/mobile như **Firebase Authentication, Cloud Firestore, Cloud Storage for Firebase, Cloud Messaging, Hosting, Remote Config** và SDK phía client.

Ví dụ công ty xây dựng ứng dụng đặt hàng:

- **Web và Android app** đăng nhập qua Firebase Authentication.
- **Cloud Firestore** giữ giỏ hàng và trạng thái giao diện cần đồng bộ gần thời gian thực.
- **Java/Spring Boot orders-api** trên Cloud Run xử lý đơn hàng có giao dịch nghiệp vụ.
- **Cloud SQL** lưu các giao dịch tài chính; **Pub/Sub** phân phối sự kiện.
- Đội vận hành dùng **Google Cloud IAM, Cloud Logging, Monitoring và Billing**.

Tất cả có thể ở trong **cùng một Google Cloud project đã bật Firebase**. Firebase console và Google Cloud console là **hai cách nhìn/quản lý một tập tài nguyên dự án chung danh tính, IAM và billing**.

~~~mermaid
flowchart TB
    ORG["Google Cloud Organization / Folders"] --> P["Google Cloud project<br/>shop-prod-001"]
    P --> F["Firebase configuration<br/>Firebase console + Apps"]
    P --> G["Google Cloud resources<br/>IAM, Cloud Run, VPC, SQL, Pub/Sub"]
    F --> WEB["Firebase Web App registration"]
    F --> AND["Firebase Android App registration"]
    F --> AUTH["Firebase Authentication"]
    F --> FS["Cloud Firestore"]
    F --> ST["Cloud Storage for Firebase"]
    G --> RUN["Cloud Run Java backend"]
    RUN --> FS
    WEB --> AUTH
    WEB --> FS
    AND --> AUTH
~~~

**Cốt lõi:** Firebase không tạo một Google Cloud project con; **Firebase project chính là Google Cloud project được bổ sung cấu hình/dịch vụ Firebase**. Khi thêm Firebase, **project ID và project number không đổi**.

## 2. Phân cấp tài nguyên và ứng dụng

| Thành phần | Vị trí trong mô hình | Ví dụ | Ý nghĩa |
|---|---|---|---|
| **Google Cloud organization/folder** | Cấp trên project nếu doanh nghiệp quản lý tập trung | org → engineering → prod | Kế thừa IAM và organization policies |
| **Google Cloud / Firebase project** | Ranh giới tài nguyên, API, billing, quyền | shop-prod-001 | Hai consoles nhìn cùng project |
| **Firebase App registration** | App web/Android/Apple trong project | shop-web, shop-android | Cấu hình client SDK, không tạo project mới |
| **Cloud Firestore database** | Database resource thuộc project | (default), orders-catalog | Collections/documents, location, Security Rules |
| **Firebase Authentication** | Dịch vụ identity của project | Người dùng web/mobile | User ứng dụng khác IAM principal của cloud |
| **Cloud Run service** | Compute resource thuộc Google Cloud project | orders-api | Java server có service identity riêng |
| **Cloud Billing account** | Tài khoản thanh toán được liên kết project | billing-account-A | Có thể thanh toán nhiều projects |

### 2.1. Firebase project khác Firebase App

Một Firebase project có thể đăng ký nhiều **Web, Android và Apple apps** chia sẻ các backend resources của project:

~~~text
Project shop-prod-001
  Firebase Web App: Shop Website (appId riêng)
  Firebase Android App: com.example.shop
  Firebase Apple App: com.example.shop.ios
  Firebase Authentication: users của project
  Cloud Firestore: dữ liệu thuộc project
  Cloud Run: orders-api server
~~~

**Ba Firebase Apps không mặc nhiên có ba databases hoặc ba hóa đơn.** Chúng có thể dùng chung backend của project, trừ khi code chủ động gọi resource khác. Nếu cần tách dữ liệu, IAM và billing giữa môi trường, hãy tạo **projects riêng** thay vì chỉ thêm một Firebase App có tên “staging”.

Tài liệu Firebase giới hạn khoảng **30 Firebase Apps mỗi project**. Không nên dùng app registration như cơ chế tạo một backend biệt lập cho từng tenant.

### 2.2. Thêm Firebase không đồng nghĩa khởi tạo mọi sản phẩm

Thêm Firebase vào Google Cloud project **không có nghĩa** đã tạo một Firestore database, một nhóm Authentication users, Storage bucket hoặc Cloud Run service. Từng sản phẩm có bước khởi tạo, API, vị trí dữ liệu, Security Rules/IAM và billing riêng. Nếu chỉ thấy project trong Firebase console, **chưa đủ để kết luận Firestore đã sẵn sàng**.

## 3. Phân biệt các định danh

| Tên | Ví dụ giả định | Có đổi được không? | Dùng vào đâu |
|---|---|---|---|
| **Project display name** | Shop Production | Có | Nhãn dễ đọc trong consoles |
| **Project ID** | shop-prod-001 | **Không sau khi provision** | gcloud, Firebase CLI, API resource names |
| **Project number** | 123456789012 | Không | IAM service agents, Firebase config, một số APIs |
| **Firebase App ID** | 1:123456789012:web:abc123 | ID được cấp khi đăng ký app | Firebase SDK/app registration |
| **Android package name** | com.example.shop | Gắn với app đã đăng ký | Android builds/SHA setup |
| **Apple bundle ID** | com.example.shop.ios | Gắn với app đã đăng ký | iOS configuration |
| **Web API key** | Giá trị trong Firebase config | Có thể thay/restrict theo nhu cầu | Định tuyến một số Firebase APIs; **không phải admin secret** |

**Project ID** là định danh duy nhất trên Google Cloud/Firebase và không sửa sau khi tài nguyên được provision. Khi xóa project, **không thể dùng lại project ID đó** cho project khác. **Project number** do Google cấp, không chỉnh sửa. **Display name** đổi được nhưng **không đổi ID trong API/CLI**.

### 3.1. Đọc metadata từ hai consoles và CLI

**Firebase console:** Project settings → **General** hiển thị project name, ID, number và danh sách Apps.

**Google Cloud console:** IAM & Admin → Settings/Project info; IAM, Billing, APIs & Services đều gắn cùng project.

~~~bash
# Đọc metadata, không thay đổi tài nguyên
gcloud projects describe shop-prod-001 \
  --format="yaml(projectId,projectNumber,name,labels,lifecycleState)"

gcloud config get-value project
firebase projects:list
~~~

Nếu Firebase CLI không liệt kê project mà Google Cloud CLI có, nguyên nhân có thể là **Firebase chưa được thêm**, principal/CLI identity khác nhau, IAM/Terms hoặc trạng thái project. **Không tạo project cùng tên để “sửa”** trước khi kiểm tra.

### 3.2. Cấu hình Web SDK

~~~javascript
// Dữ liệu minh họa; lấy đúng config của app từ Firebase Project settings.
const firebaseConfig = {
  apiKey: "EXAMPLE_PUBLIC_WEB_API_KEY",
  authDomain: "shop-prod-001.firebaseapp.com",
  projectId: "shop-prod-001",
  appId: "1:123456789012:web:example"
};
~~~

Config Web/Android/Apple giúp client SDK tìm đúng project và app registration. Các trường như **apiKey/projectId** không phải quyền quản trị, nhưng **API key cần restrictions phù hợp**; Firestore dữ liệu vẫn phải được bảo vệ bằng **Firebase Authentication + Security Rules** hoặc IAM ở phía server. Không lấy việc API key hiển thị công khai làm bằng chứng backend an toàn hay không an toàn.

## 4. Tạo project mới hay thêm Firebase vào project có sẵn?

| Trường hợp | Hành động | Kết quả |
|---|---|---|
| Chưa có Google Cloud project | Firebase console → Create a project; hoặc Firebase CLI tạo | Tạo Google Cloud project mới rồi thêm Firebase |
| Có Cloud Run/VPC/SQL trong Google Cloud project | Firebase console → Add Firebase to Google Cloud project | **Bổ sung Firebase vào project hiện có**, giữ resource IDs/IAM/billing |
| Có nhiều projects dev/prod | Bật Firebase ở từng project nếu cần | Ranh giới môi trường riêng |

### 4.1. Kiểm tra trước khi thêm Firebase

1. Xác nhận **project ID**, organization/folder, owner và môi trường.
2. Kiểm tra IAM và **Firebase Terms of Service** đã được tài khoản chấp nhận (qua Firebase console).
3. Kiểm tra Cloud Billing account; có billing có thể làm Firebase project dùng **Blaze**.
4. Xem các dịch vụ đang có (Cloud SQL/Cloud Run/Firestore), vị trí dữ liệu và quyền.
5. Quyết định có dùng **Google Analytics** hay không: là lựa chọn tùy chọn trong setup, có ràng buộc về location/data sharing.

### 4.2. Thêm Firebase qua console

1. Đăng nhập **Firebase console** bằng tài khoản có quyền với Google Cloud project.
2. Chọn **Create a project**, rồi **Add Firebase to Google Cloud project**.
3. Tìm, chọn chính xác project đã chuẩn bị; review **ID và organization**.
4. Chấp nhận điều khoản nếu được yêu cầu, review tùy chọn Google Analytics.
5. Chọn **Add Firebase**, sau đó so ID/number ở **Project settings → General** với gcloud.

### 4.3. Dùng Firebase CLI

~~~bash
# Chỉ liệt kê trước
firebase login
firebase projects:list

# THAO TÁC CÓ TÁC ĐỘNG: chọn project có sẵn theo prompt.
firebase projects:addfirebase

# Tạo Google Cloud project mới rồi bật Firebase là thao tác KHÁC:
# firebase projects:create my-new-firebase-project
~~~

**Không tạo project mới** nếu mục tiêu là dùng lại Cloud Run, IAM và billing hiện có. Khi gọi programmatically, có thể dùng **Firebase Management API projects.addFirebase** hoặc Terraform resource **google_firebase_project** theo quy trình IaC.

### 4.4. Điều gì xảy ra khi thêm Firebase?

Theo tài liệu Firebase, thao tác add Firebase có thể:

- Bật các Firebase-related APIs và dịch vụ nền cần thiết.
- Tạo **Firebase service agent** và Firebase Admin SDK service account của project.
- Tạo một **browser API key** có restrictions mặc định cho các API Firebase liên quan.
- Thêm project label **firebase:enabled**.

**Không tự tạo label này để giả vờ đã bật Firebase.** Quan trọng hơn, **thao tác Add Firebase không có cơ chế undo hoàn toàn được hỗ trợ**. Việc tắt APIs/xóa service accounts/keys thủ công có thể làm dịch vụ đang phụ thuộc bị lỗi. Hãy review như một thay đổi project dài hạn.

**Quyền tối thiểu để thêm Firebase** theo tài liệu bao gồm **firebase.projects.update**, **resourcemanager.projects.get**, **serviceusage.services.enable** và **serviceusage.services.get**. Không cấp Owner cho mọi người chỉ để qua bước này; phân công người có quyền thích hợp và xác nhận quy trình.

## 5. Một hệ thống IAM và tổ chức dự án dùng chung

Firebase project **không sở hữu một bộ Google Cloud IAM độc lập**. Quyền của principals trên Google Cloud project cũng áp dụng với tài nguyên Firebase tương ứng; các role được cấp trong Firebase console được phản ánh trong **Google Cloud IAM**.

| Người dùng/danh tính | Thường làm gì | Nguyên tắc cấp quyền |
|---|---|---|
| **Project administrator** | Thêm Firebase, quản lý cấu hình project | Quyền quản trị qua IAM, phê duyệt và audit |
| **Firebase developer** | Quản lý Firebase Apps, Hosting, Rules theo nhiệm vụ | Role Firebase/product-specific, hạn chế toàn project |
| **Data administrator** | Thiết kế Firestore database/indexes, data migrations | Vai trò Firestore/Datastore theo phạm vi cần thiết |
| **Cloud Run runtime SA** | Java đọc/ghi Firestore và gọi API Google Cloud | Chỉ quyền cần thiết trên Firestore/Storage |
| **Firebase service agent** | Hỗ trợ vận hành dịch vụ Firebase | Service identity do Google quản lý; không xóa tùy tiện |
| **Mobile/web end user** | Đăng nhập app và truy cập dữ liệu client | **Firebase Authentication + Security Rules**, không cấp project IAM |

### 5.1. Firebase console và Cloud console hiển thị IAM khác nhau

**Firebase console → Project settings → Users and permissions** chỉ hiển thị một phần principals được cấp basic/Firebase roles; không phải toàn bộ IAM policy của Google Cloud project. **Service accounts và roles rộng hơn** cần kiểm tra ở **Google Cloud console → IAM & Admin → IAM**.

Ví dụ lệnh chỉ đọc:

~~~bash
gcloud projects get-iam-policy shop-prod-001 \
  --format="table(bindings.role,bindings.members)"
~~~

Lệnh trên cho phép nhìn tổng quan bindings project; để đánh giá **quyền hiệu lực**, còn phải xem quyền kế thừa từ organization/folder, IAM Conditions, custom roles, resource-level policies và deny policies. Không kết luận một principal không có quyền chỉ vì không thấy trong trang Users and permissions của Firebase.

### 5.2. Organization policies áp dụng cho cả Firebase

Nếu project nằm dưới một Google Cloud organization/folder, nó **kế thừa organization policies**, ví dụ hạn chế vùng tạo tài nguyên, service-account key creation, allowed services hoặc IAM domains. Việc mở Firebase console **không bypass** org policies.

Khi thêm Firebase thất bại do chặn API, không nên tự chuyển project production khỏi organization để “vượt rào”; cần cùng platform/security team điều chỉnh quyền hoặc chọn sản phẩm/location phù hợp.

### 5.3. Firebase Authentication user khác Cloud IAM principal

Một end user có **Firebase Auth UID** (ví dụ u_456) không phải là một Google Cloud service account hay IAM user. Client SDK dùng Firebase Auth ID token để Security Rules kiểm tra **request.auth.uid**; không cấp **roles/editor** hoặc **roles/datastore.user** trên project cho từng khách hàng.

**Firebase Authentication** cung cấp danh tính ứng dụng. **Google Cloud IAM** kiểm soát các principal triển khai và truy cập server APIs. Đây là hai lớp cần dùng đúng ngữ cảnh.

## 6. Firestore Security Rules và IAM không thay thế nhau

Cloud Firestore là tài nguyên Google Cloud nằm trong Firebase project. Tuy nhiên cách kiểm soát quyền **phụ thuộc đường truy cập**.

| Nguồn truy cập | Xác thực | Kiểm soát quyền chủ yếu |
|---|---|---|
| **Web/Android/Apple Firebase client SDK** | Firebase Authentication hoặc không đăng nhập | **Cloud Firestore Security Rules** |
| **Java server trên Cloud Run** dùng Admin SDK/Google Cloud Firestore server SDK | **ADC**/Cloud Run service identity | **Google Cloud IAM** |
| **GKE Java worker** qua server client library | Workload Identity Federation/ADC | **Google Cloud IAM** |
| **Firebase console / Cloud console administrators** | Google accounts có role | IAM/admin permissions |

**Điểm dễ nhầm:** Server SDK/Admin SDK **bỏ qua Cloud Firestore Security Rules** và xác thực thông qua IAM. Vì vậy một ruleset khóa toàn bộ client **không chặn** server có IAM Datastore/Firestore đủ quyền. Ngược lại, cấp IAM cho backend **không cho phép** người dùng web bỏ qua Security Rules.

### 6.1. Ví dụ rules giới hạn mỗi user xem dữ liệu của mình

~~~text
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{userId} {
      allow read, write: if request.auth != null
                         && request.auth.uid == userId;
    }
  }
}
~~~

Ví dụ chỉ áp dụng cho tài liệu **/users/{uid}**. Các đường dẫn khác không được tự động cho phép. Trước production phải bổ sung kiểm tra **schema fields, hạn mức kích thước, vai trò, quy tắc cập nhật** và dùng **Local Emulator Suite** để kiểm thử truy cập trái phép.

**Không dùng allow read, write: if true** để “sửa lỗi quyền” trong production. Nếu Java server được IAM cho phép, việc đổi Security Rules không làm nó ít quyền hơn.

### 6.2. Đổi Security Rules có thể ảnh hưởng toàn bộ Firebase Apps

Nếu web và Android cùng trỏ tới project **shop-prod-001**, deploy một ruleset chung có thể thay đổi quyền cả hai apps. Khi dùng CLI, thao tác **firebase deploy --only firestore** có thể ghi đè rules/index configuration hiện có theo firebase.json. Cần review diff, kiểm thử trên emulator/staging và dùng pipeline có phê duyệt.

Khi có nhiều Firestore databases trong cùng project, mỗi database có cấu hình/rules cần xét riêng. Đừng cho rằng một ruleset ở default database luôn bao phủ mọi database trong project.

## 7. Billing chung: Spark, Blaze và các dịch vụ Google Cloud

Tài khoản thanh toán gắn với **Google Cloud project**, không phải Firebase App. Do đó nếu cùng project có Cloud Run, Cloud SQL, Firestore và Hosting thì chi phí được ghi nhận vào cùng project/billing account theo từng SKU.

| Gói Firebase | Ý nghĩa | Lưu ý |
|---|---|---|
| **Spark** | No-cost plan, sản phẩm/quota trong phạm vi miễn phí | Không cấp quyền sử dụng mọi Google Cloud dịch vụ trả phí; vượt quota có thể làm sản phẩm ngừng phục vụ |
| **Blaze** | Pay-as-you-go khi project liên kết Cloud Billing account | Một số sản phẩm có free allowance, nhưng sử dụng vượt ngưỡng sẽ tính phí |

**Khi thêm Firebase vào một Google Cloud project đã bật billing, Firebase sẽ dùng Blaze.** Liên kết Cloud Billing account với Firebase project cũng có thể **tự chuyển sang Blaze**. Không có một “Firebase billing” riêng cho từng App registration trong cùng project.

### 7.1. Ví dụ tính tổng chi phí

Một project production có thể bị tính phí qua các thành phần:

| Thành phần | Nguồn phát sinh |
|---|---|
| **Cloud Firestore** | Document reads/writes/deletes, storage, network, index-related usage và features theo gói |
| **Cloud Storage for Firebase** | Bucket bytes, operations, outbound/egress |
| **Cloud Run/Cloud SQL** | Compute, memory, database storage, networking |
| **Firebase Hosting/App Hosting** | Storage, build, bandwidth/runtime theo sản phẩm |
| **Cloud Logging/Monitoring** | Ingestion, retention, metrics/alerts theo mức tính phí |
| **Firebase Authentication** | Giá và giới hạn thay đổi theo phương thức/identity product |

Không viết một giá cố định cho “Firebase project” vì hóa đơn chủ yếu do **mức sử dụng từng dịch vụ** và cấu hình tài nguyên tạo ra.

### 7.2. Thực hành kiểm tra trước khi bật Blaze

~~~bash
# Chỉ đọc metadata và tình trạng account liên kết.
gcloud projects describe shop-prod-001 \
  --format="yaml(projectId,projectNumber)"

gcloud billing projects describe shop-prod-001
~~~

Người thực hiện cần quyền xem Cloud Billing, ví dụ project billing information permission tương ứng. Nếu báo PERMISSION_DENIED, không suy rằng project không có billing. Kiểm tra với Billing administrator.

**Cloud Billing budget alerts chỉ cảnh báo, không tự chặn chi phí hoặc dừng Firestore/Cloud Run.** Tách project staging/prod giúp đặt ngân sách, IAM và alert riêng, nhưng không thay thế quota/capacity planning.

## 8. Thêm Firebase App đúng project và đúng nền tảng

Sau khi bật Firebase, bạn đăng ký Firebase Apps **trong project đã chọn**. Mỗi app nhận cấu hình theo platform.

| Platform | Định danh cần chuẩn bị | File/object cấu hình |
|---|---|---|
| **Web** | Firebase App nickname/registration | JavaScript firebaseConfig |
| **Android** | Package name, có thể thêm SHA fingerprints cho tính năng xác thực | google-services.json |
| **Apple** | Bundle ID và các settings theo sản phẩm | GoogleService-Info.plist |

**Firebase App nickname không phải project ID**. File config được tải từ Firebase console; không tự tạo App ID giả để deploy app thật.

### 8.1. Xem apps đã đăng ký bằng CLI

~~~bash
firebase projects:list

# Dùng đúng project ID của môi trường.
firebase apps:list --project shop-dev-001

# Xem cấu hình Web app đã có (thay FIREBASE_APP_ID bằng ID thật).
firebase apps:sdkconfig WEB FIREBASE_APP_ID \
  --project shop-dev-001
~~~

Đây là các lệnh đọc thông tin. Nếu app chưa tồn tại, phải **đăng ký app trước** trong Firebase console hoặc qua firebase apps:create theo platform. **Không chọn production project chỉ vì nó xuất hiện đầu danh sách**.

### 8.2. Web API key không phải khóa Admin SDK

**Web app config chứa API key công khai theo thiết kế**; cần API/application restrictions theo tài liệu Google Cloud và các controls như Auth, Firestore Security Rules, App Check tùy sản phẩm. Khóa này **không** đồng nghĩa mật khẩu DB hoặc service-account private key. Ngược lại, **service-account JSON private key** là thông tin bí mật nguy hiểm, không được nhúng trong web bundle, mobile APK/IPA, Git hay public Hosting.

### 8.3. Google Analytics là lựa chọn liên kết riêng

Tạo Firebase project có thể hỏi có dùng **Google Analytics** hay không. Liên kết Analytics property có cơ chế báo cáo, location và data sharing riêng; **không tự coi một Firestore database là Google Analytics dataset**. Analytics cũng không phải phương án backup dữ liệu Firestore. Nếu không dùng Google Analytics, vẫn có thể dùng các Firebase sản phẩm được hỗ trợ khác.

## 9. Thiết kế tách môi trường dev, staging và production

Một doanh nghiệp nên coi **project** là ranh giới cô lập quan trọng cho dữ liệu, IAM, resource quotas, API keys và billing:

| Môi trường | Google Cloud/Firebase project | Dữ liệu | Quyền và quy trình |
|---|---|---|---|
| **Development** | shop-dev-001 | Dữ liệu giả/ẩn danh | Developers được thử nghiệm, ngân sách nhỏ |
| **Staging** | shop-stage-001 | Dataset gần production nhưng đã khử nhạy cảm | CI/CD và QA, kiểm thử rules, migration |
| **Production** | shop-prod-001 | Dữ liệu khách hàng thật | Quyền tối thiểu, release approval, backup và alerts |

**Không dùng một project production rồi tạo Firebase apps tên dev, stage và prod để thay cho tách môi trường.** Chúng vẫn chia sẻ IAM, Firebase Authentication user store và nhiều backend resources của project.

### 9.1. Firebase CLI project aliases

Tại thư mục dự án app frontend có Firebase CLI configuration:

~~~bash
firebase use --add
firebase use

# Chỉ khi đã cấu hình alias tương ứng:
firebase use dev

# Khi deploy luôn chỉ rõ project/alias để giảm nhầm lẫn.
# Sau khi review ruleset, thay đổi này sẽ tác động tới môi trường dev.
firebase deploy --only firestore:rules --project dev
~~~

Một file **.firebaserc** trong dự án mã nguồn (minh họa, bài học không tạo file):

~~~json
{
  "projects": {
    "dev": "shop-dev-001",
    "staging": "shop-stage-001",
    "prod": "shop-prod-001"
  }
}
~~~

Các aliases giúp chọn project đúng nhưng **không tự cấp quyền** và **không khóa môi trường production**. CI nên chỉ định project ID/alias rõ, tách credentials và required approvals; không dựa duy nhất vào project đang active trên laptop.

### 9.2. Cấu hình mobile/web theo build variant

- **Android:** dùng google-services.json theo product flavor/build variant, kiểm tra package name/SHA certificates.
- **Apple:** dùng GoogleService-Info.plist đúng build target/bundle ID.
- **Web:** dùng firebaseConfig riêng cho dev/prod; projectId và appId phải đi cùng nhau đúng app đã đăng ký.
- **Java backend:** dùng service account của Cloud Run project; cấu hình project ID phải khớp dữ liệu backend muốn truy cập.

Nhầm file config sẽ khiến **app dev gửi dữ liệu vào production project** ngay cả khi backend riêng. Trong review release cần xác nhận **project ID/appId hiện tại**, không chỉ domain URL hoặc môi trường NODE_ENV/SPRING_PROFILES_ACTIVE.

### 9.3. Emulator không thay production rules testing

**Firebase Local Emulator Suite** cho phép thử Firestore, Auth và một số Firebase services cục bộ:

~~~bash
# Từ một source project đã có firebase.json cấu hình emulator:
firebase emulators:start --only auth,firestore --project demo-shop-dev
~~~

ID có tiền tố **demo-** dành cho môi trường mô phỏng giúp giảm nguy cơ chạm dịch vụ cloud thật khi chỉ chạy các emulator được hỗ trợ. Tuy nhiên **không phải mọi sản phẩm hoặc API đều được mô phỏng**; nếu code gọi dịch vụ không có emulator, phải xác minh hành vi fail/route trước khi chạy tests.

## 10. Java/Cloud Run backend sử dụng cùng Google Cloud project

Một dịch vụ Java trên Cloud Run có thể dùng **Firebase Admin SDK** để xác minh Firebase Authentication tokens hoặc đọc Cloud Firestore. Trong hạ tầng Google Cloud, **Application Default Credentials (ADC)** dùng service identity ngắn hạn thay cho tệp JSON service account key.

### 10.1. Ví dụ Java khởi tạo Firebase Admin SDK

Thêm thư viện **com.google.firebase:firebase-admin** vào Java project theo phiên bản được CI khóa và kiểm tra lỗ hổng. Ví dụ Java:

~~~java
import com.google.auth.oauth2.GoogleCredentials;
import com.google.cloud.firestore.DocumentSnapshot;
import com.google.cloud.firestore.Firestore;
import com.google.firebase.FirebaseApp;
import com.google.firebase.FirebaseOptions;
import com.google.firebase.cloud.FirestoreClient;

public final class FirebaseProjectProbe {
    private FirebaseProjectProbe() {}

    public static void main(String[] args) throws Exception {
        String projectId = "shop-dev-001"; // Chọn bằng cấu hình môi trường.

        FirebaseOptions options = FirebaseOptions.builder()
            .setCredentials(GoogleCredentials.getApplicationDefault())
            .setProjectId(projectId)
            .build();

        FirebaseApp app = FirebaseApp.initializeApp(options);
        Firestore firestore = FirestoreClient.getFirestore(app);
        try {
            DocumentSnapshot document = firestore.collection("healthchecks")
                .document("lab-example")
                .get()
                .get();
            System.out.println("Firestore request OK; exists=" + document.exists());
        } finally {
            firestore.close();
            app.delete();
        }
    }
}
~~~

**Điều kiện:** database Firestore đã được tạo, API bật, ADC principal có IAM phù hợp. Tài liệu ví dụ cho thấy cách xác định **projectId**; **trong ứng dụng thật** chọn project theo environment config và khởi tạo SDK một lần lúc startup (không tạo/xóa FirebaseApp theo từng HTTP request).

**Không hardcode production service account JSON private key hoặc GOOGLE_APPLICATION_CREDENTIALS trỏ tới khóa lưu trong image.** Với Cloud Run, cấp role tối thiểu cho runtime service account; với GKE, dùng Workload Identity Federation.

### 10.2. Chọn service account cho Cloud Run

~~~bash
# Chỉ đọc service identity và project trước khi thay đổi.
gcloud run services describe orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --format="yaml(spec.template.spec.serviceAccountName,status.url)"

# Thao tác có tác động, chỉ chạy sau khi IAM và môi trường đã được review.
gcloud run services update orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --service-account=orders-runtime@shop-dev-001.iam.gserviceaccount.com
~~~

Nếu Java SDK truy cập Firestore, principal cần các **Firestore IAM permissions** tương ứng; role **roles/datastore.user** là một lựa chọn predefined tương đối rộng cho đọc/ghi, không mặc định là least privilege. Cân nhắc roles/custom permissions hoặc tách service theo use case.

**Quan trọng:** project của Cloud Run service và project chứa Firestore database **có thể khác nhau**. Nếu Java chọn projectId khác, phải xem **cross-project IAM và resource policies**, không tự động cấp Owner trên hai projects.

### 10.3. Phân biệt client Firebase Auth và server verification

~~~mermaid
sequenceDiagram
    participant U as Mobile/Web app
    participant AUTH as Firebase Authentication
    participant API as Cloud Run Java API
    participant FS as Cloud Firestore
    U->>AUTH: Sign in
    AUTH-->>U: ID token
    U->>API: HTTPS + ID token
    API->>API: Verify signature, issuer, audience/project
    API->>FS: Firestore Admin SDK, ADC/IAM
    FS-->>API: Document response
    API-->>U: Business response
~~~

Server phải **xác minh Firebase ID token** theo Firebase Admin SDK (signature, issuer, audience/project và expiry), không tin client gửi user ID trong JSON. Firebase Authentication token của khách hàng **không phải** Google Cloud IAM access token. Khi Java server gọi Firestore Admin SDK, **Security Rules không được thực thi**; backend phải kiểm tra quyền nghiệp vụ theo user ID/claims trước khi truy vấn.

## 11. Ranh giới project không phải ranh giới location

**Firebase/Google Cloud project không có một vị trí lưu trữ duy nhất cho mọi sản phẩm.** Từng resource có location riêng: Cloud Run region, Cloud SQL region, Firestore database location, Storage bucket location, Analytics reporting location.

| Resource | Quyết định location | Điều cần đánh giá |
|---|---|---|
| **Cloud Firestore database** | Chọn lúc tạo database | Region/multiregion, residency, độ trễ, khả năng đổi location |
| **Cloud Run orders-api** | Chọn region deploy | Gần Firestore/SQL và người dùng |
| **Cloud SQL** | Chọn region khi tạo instance | Private networking, HA, backup/DR |
| **Cloud Storage bucket** | Chọn location theo bucket | Residency, egress, lifecycle |
| **Google Analytics** | Reporting location/property config | Compliance và điều khoản dữ liệu |

Nếu project Firebase được đặt tên **shop-vn-prod**, điều đó **không bảo đảm** Firestore/Analytics/Storage nằm ở Việt Nam. Khi cần data residency, phải kiểm tra resource locations và organization policies riêng; cấu hình Firestore database location phải quyết định thận trọng vì không thể đổi đơn giản cho database đã tạo.

**Mẫu kiến trúc:** Cloud Run Java ở asia-southeast1, Firestore gần backend theo locations hỗ trợ, Cloud SQL có region riêng, Storage/Analytics theo quy định. Nếu các thành phần ở regions khác, tính thêm độ trễ giữa dịch vụ và phí truyền dữ liệu. Không suy rằng Firebase console tự làm mọi service đồng vùng.

## 12. Quản lý vòng đời project, thay đổi và xóa dữ liệu

### 12.1. Không có hai nút Delete project độc lập

**Xóa Firebase project cũng xóa Google Cloud project bên dưới**, gồm các tài nguyên Google Cloud như Cloud Run, Cloud SQL, IAM, Storage và APIs thuộc project theo quy trình xóa và retention áp dụng. Ngược lại, xóa Google Cloud project cũng xóa Firebase project tương ứng.

**Không nhầm ba thao tác:**

| Thao tác | Tác động |
|---|---|
| **Xóa một Firebase App registration** | Gỡ đăng ký của client app; không đồng nghĩa xóa cả project/Firestore data |
| **Xóa một Firestore database/bucket** | Xóa tài nguyên hoặc dữ liệu sản phẩm đó; có thể ảnh hưởng nhiều Firebase Apps |
| **Xóa Firebase / Google Cloud project** | Tác động đến toàn bộ tập tài nguyên project, có thể mất dữ liệu không khôi phục được |

Google Cloud có **cửa sổ shutdown/recovery** cho project đã yêu cầu xóa, nhưng **không coi đó là backup hoặc cam kết mọi dữ liệu đều khôi phục được**. Trước các thao tác xóa cần inventory, backup/export, xác minh owner, legal retention, chi phí, dependencies và phê duyệt change control.

### 12.2. Có thể “gỡ Firebase” rồi giữ nguyên project không?

Sau khi thêm Firebase vào Google Cloud project, **không có cơ chế gỡ Firebase hoàn toàn được hỗ trợ** để đưa project trở về đúng trạng thái cũ. Bạn có thể ngừng dùng các sản phẩm Firebase và có những thao tác xóa thủ công, nhưng việc xóa service accounts, APIs, browser key hoặc label có thể phá vỡ các tính năng Firebase/Google Cloud đang phụ thuộc.

**Khi không chắc tác động, để nguyên cấu hình và hỏi người quản trị**, thay vì xóa toàn bộ Firebase service identities chỉ vì ứng dụng mobile đã ngừng dùng.

### 12.3. Backup và phục hồi phải theo từng sản phẩm

- **Cloud Firestore:** tính tới managed backups/export, PITR khi được hỗ trợ, retention và restore rehearsal.
- **Cloud SQL:** backup/PITR riêng của database instance.
- **Cloud Storage:** versioning/lifecycle/backup theo yêu cầu và tính năng.
- **Firebase Authentication:** dữ liệu users cần có kế hoạch export/restore và yêu cầu quyền riêng.
- **Google Analytics:** retention/reporting riêng; không thay thế backup của ứng dụng.

**Một bản export Firestore không sao lưu toàn bộ Firebase project** gồm IAM, Firebase App registrations, Authentication configuration, Hosting/Cloud Run/SQL. Hãy quản lý cấu hình bằng IaC, Git review và runbook khôi phục liên dịch vụ.

## 13. Quan sát hoạt động và kiểm soát chi phí từ hai consoles

### 13.1. Dashboard nào giải quyết câu hỏi nào?

| Câu hỏi | Nơi xem ưu tiên |
|---|---|
| Firebase Apps nào đã đăng ký? | Firebase console → Project settings → General |
| Firestore reads/writes, rules và indexes? | Firebase console → Firestore; Google Cloud Firestore metrics |
| Ai sửa project IAM? | Google Cloud IAM & Admin, Cloud Audit Logs |
| Cloud Run Java bị HTTP 5xx? | Cloud Logging/Monitoring, Cloud Run service metrics |
| Billing tăng do Firestore hay Cloud Run? | Cloud Billing reports (lọc project/service/SKU) |
| App crash ở Android/iOS? | Firebase Crashlytics |
| Mobile analytics theo app? | Google Analytics for Firebase, nếu đã liên kết |

**Firebase project có chung billing, nhưng không có một dashboard duy nhất thay thế toàn bộ Cloud Monitoring/Cloud Billing.** Khi điều tra sự cố, nên ghi lại project ID, thời điểm, service/app registration và affected users; sau đó chuyển giữa consoles mà giữ đúng project.

### 13.2. Các guardrails vận hành

1. **Project labels** cho env, team, cost-center và data-classification; phân tách Google Cloud resources bằng naming conventions.
2. **Budgets và alerts** riêng cho dev/staging/prod, đồng thời đặt quota/API limits theo workload.
3. **Least privilege IAM**, review service accounts còn sống và keys không dùng, audit thay đổi Rules/Storage/API.
4. **Security Rules automated tests** qua emulator; verify Java server authorization vì Admin SDK bypasses Rules.
5. **Monitoring** cho Firestore reads/writes/errors, Cloud Run latency, auth failures, storage usage và chi phí.
6. **Release workflow** có người duyệt khi thay Firebase rules, Cloud IAM, billing hoặc data location.

Không coi **Spark** là một “hard cap” tài chính an toàn cho toàn bộ công nghệ: giới hạn sản phẩm và khả năng dùng paid Google Cloud services khác nhau. **Blaze không có ngưỡng miễn phí vô hạn**; khi sử dụng trả phí vượt free allowance, hóa đơn vẫn tăng.

## 14. Troubleshooting quan hệ Firebase và Google Cloud project

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra |
|---|---|---|
| Firebase console không thấy project Google Cloud | Chưa bật Firebase, principal thiếu quyền, chưa chấp nhận Terms | Project ID, IAM, Terms, dùng CLI/REST |
| Thêm Firebase báo **403 PERMISSION_DENIED** | Thiếu firebase.projects.update hoặc serviceusage permissions | Google Cloud IAM, org policies, Firebase Terms |
| Chỉ sửa label firebase:enabled nhưng không thấy Firebase Apps | Label không tự khởi tạo Firebase services | Dùng Firebase console/CLI/Management API đúng |
| Project ID không đổi được | ID cố định sau provisioning | Dùng display name hoặc tạo project mới với migration |
| Firebase app dev đọc dữ liệu production | Client config nhầm projectId/appId hoặc build variant | File config theo env, Firebase SDK options |
| Google Cloud console có user, Firebase Users and permissions không hiển thị | Firebase console chỉ hiển thị tập role/principal hạn chế | IAM & Admin → IAM, service accounts |
| Firestore client bị **PERMISSION_DENIED** | Chưa đăng nhập hoặc Security Rules từ chối | Firebase Auth UID, Rules simulator, emulator tests |
| Java Admin SDK đọc Firestore được dù client Rules deny | Server SDK dùng IAM, bỏ qua Firestore Rules | Cloud Run runtime SA, code kiểm tra quyền nghiệp vụ |
| Java server bị 403 trong cùng project | Runtime SA thiếu IAM; không phải Firebase user thiếu role | ADC, IAM effective permissions, API enabled |
| Client dùng API key đúng nhưng dữ liệu lộ | Rules yếu hoặc truy cập backend sai kiểm soát | Rules tests, App Check/Authentication, server authorization |
| Sau bật billing Firebase chuyển Blaze | Google Cloud project được liên kết Cloud Billing | Billing project info, Firebase usage and billing |
| Firebase project vẫn có chi phí dù xóa Web App | Cloud Run/SQL/Storage/Firestore vẫn đang chạy | Billing by service/SKU, inventory resources |
| Thay Rules từ CLI khiến app khác lỗi | Nhiều Firebase Apps cùng project/ruleset | firebase.json, deploy history, test staging |
| Tạo Firestore location sai | Project name không ấn định resource region | Firestore database location, data migration plan |
| Xóa project làm mất cả Cloud Run/Cloud SQL | Firebase và Google Cloud là cùng project | Project deletion recovery/backup plan |

### Runbook chẩn đoán theo thứ tự

1. **Xác nhận project ID/number** ở Firebase và Google Cloud consoles.
2. **Xác nhận danh tính** thực hiện thao tác: Firebase CLI account, gcloud account, Java ADC, Firebase Auth user — không hoán đổi.
3. **Xác nhận loại resource**: project, Firebase App registration, Firestore database, Cloud Run service hay Billing account.
4. **Chọn đúng lớp bảo mật**: Firebase Security Rules cho client, IAM cho server/Admin SDK, App Check/Auth theo thiết kế.
5. **Kiểm tra môi trường và config**: dev/staging/prod aliases, appId, service account, secrets, API restrictions.
6. **Đối chiếu billing và logs**, sau đó sửa tối thiểu và kiểm thử âm tính trên staging trước production.

Không “chữa” mọi lỗi 403 bằng cách cấp **Owner** hoặc mở Firestore Rules public. Hai thao tác đó thường tạo rủi ro lớn hơn lỗi ban đầu.

## 15. Tình huống tổng hợp: sản phẩm Java và ứng dụng di động

Đội **Hướng Dương** xây dựng ứng dụng giao hàng:

| Thành phần | Development | Production |
|---|---|---|
| Google Cloud/Firebase project | shop-dev-001 | shop-prod-001 |
| Firebase Web/Android app | Dev build variants | Release builds |
| Firebase Authentication | Test users | Real users |
| Cloud Firestore | Fake documents + restrictive rules | Customer documents + reviewed rules |
| Java/Spring Boot API | Cloud Run dev | Cloud Run prod |
| Cloud SQL | Test orders | Production transactions |
| Billing | Nhỏ, cảnh báo thấp | Budget/SLO/alert có owner |
| IAM | Developers trong dev | Runtime SA tối thiểu, release approvers |

### 15.1. Quy trình đưa Firebase vào kiến trúc đã có

~~~mermaid
flowchart TD
    A["Google Cloud project đã có Cloud Run/SQL"] --> B["Review IAM, org policies, Billing"]
    B --> C["Add Firebase vào chính project đó"]
    C --> D["Xác minh project ID / number không đổi"]
    D --> E["Register Web/Android Firebase Apps"]
    E --> F["Create Firestore + Authentication config"]
    F --> G["Test client Security Rules bằng emulator"]
    G --> H["Cloud Run Java Admin SDK bằng ADC/IAM"]
    H --> I["Kiểm tra logs, billing, backup"]
    I --> J["Release staging → production"]
~~~

### 15.2. Test chấp nhận trước production

| Phép thử | Kỳ vọng |
|---|---|
| GCP project trước/sau Add Firebase | **Cùng project ID và number** |
| Firebase project chỉ có web app đăng ký | Không tự tạo Cloud SQL/Firestore database |
| Web app dev dùng firebaseConfig dev | Không đọc/ghi Firestore production |
| User A truy cập document của user B | Bị Security Rules từ chối |
| Java Admin SDK đọc Firestore | Cần runtime IAM, không phụ thuộc Security Rules client |
| Runtime SA không có Firestore IAM | Bị server API từ chối |
| CI deploy rules với alias dev | Không đổi production rules |
| Liên kết Cloud Billing account | Hiểu và kiểm tra chuyển sang Blaze |
| Chọn Firestore location | Được review residency/latency trước khi tạo |
| Xóa một Firebase App registration test | Không được hiểu là xóa project hoặc backend data |

### 15.3. Hệ quả khi thiết kế sai

Nếu app staging vô tình trỏ Firebase production, QA có thể ghi dữ liệu giả vào hệ thống thật, gây sai metrics và chi phí; thậm chí app client có thể truy cập dữ liệu nhạy cảm nếu Rules không đủ chặt. Nếu admin xóa “Firebase project test” mà đó thực ra là project Google Cloud dùng Cloud Run production, hậu quả có thể bao trùm cả hệ thống.

**Biện pháp then chốt:** đặt tên môi trường rõ ràng, chặn deploy nhầm qua CI approvals, dùng IAM/Roles và Security Rules đúng chỗ, backup theo từng dịch vụ, kiểm tra project ID trong release artifacts và giám sát phí theo project/service.

## 16. Bài tập và đáp án

### Bài tập A — Một hay hai project?

**Tình huống:** shop-prod-001 là Google Cloud project có Cloud Run. Nhóm “Add Firebase” vào project đó, rồi đăng ký hai Firebase Apps.

**Hỏi:** Có bao nhiêu Google Cloud projects được tạo thêm? Có bao nhiêu Firebase Apps?

**Đáp án:** **Không có Google Cloud project mới**; project ban đầu được bật Firebase. Có **hai Firebase App registrations**, không phải hai Firebase projects.

### Bài tập B — Project ID và display name

Nhóm đổi display name từ “Shop Test” thành “Shop Production”, nhưng các CLI commands vẫn tham chiếu shop-test-001.

**Đáp án:** Display name không đổi **project ID**. Muốn tách production phải tạo project riêng, migrate/configure resources và client app registrations; không đổi tên rồi giả định đã có môi trường production mới.

### Bài tập C — Quyền ở Firebase console

Một Cloud Run service account không xuất hiện trong Firebase Project settings → Users and permissions nhưng Java vẫn đọc Firestore được.

**Đáp án:** Firebase console không hiển thị mọi IAM principal/service account. Xem **Google Cloud IAM**, runtime ADC identity và roles hiện hành. Java server SDK dùng IAM, không phụ thuộc Firestore client Security Rules.

### Bài tập D — Lỗi 403

Mobile app của user A bị từ chối đọc tài liệu của user B, còn Java backend với service account được phép đọc cả hai.

**Đáp án:** Nếu Rules đang dùng request.auth.uid == userId, đây là **đúng thiết kế** với client. Java backend qua Admin SDK không dùng Security Rules, nên phải tự xác thực/authorize từng request nghiệp vụ. Không mở toàn bộ rules để mobile app đọc được.

### Bài tập E — Billing Spark và Blaze

Tổ chức có một Google Cloud project với Cloud Billing account đã bật, sau đó thêm Firebase. Kỹ sư dự đoán vẫn ở Spark nên Cloud Run luôn miễn phí.

**Đáp án:** Sai. Google Cloud project đã liên kết Billing sẽ dùng Firebase **Blaze**, với chi phí tính theo từng dịch vụ; Cloud Run/Cloud SQL và Firestore có giới hạn/quota/bảng giá riêng. **Budget alerts không tự ngắt hóa đơn**.

### Bài tập F — Tách dev và prod

Một Firebase project có ba app registrations tên “mobile-dev”, “mobile-stage” và “mobile-prod”.

**Hỏi:** Đã tách data/IAM/billing chưa?

**Đáp án:** **Chưa.** Chúng nằm trong một project; cần **Google Cloud/Firebase projects tách biệt** cho dev/staging/prod rồi cấu hình Firebase SDK, CLI aliases, service accounts và tests.

### Bài tập G — Web API key và service account key

Review phát hiện firebaseConfig Web có API key và appId, trong khi private service-account JSON key bị commit vào frontend.

**Đáp án:** Firebase Web API key là config client cần hạn chế sử dụng API/application thích hợp, không phải quyền Admin. **Service-account private key là bí mật nghiêm trọng**, cần revoke/rotate ngay, xóa khỏi mã và lịch sử phát hành phù hợp, dùng ADC/service identity trên server thay thế.

### Bài tập H — Thêm Firebase thất bại

Chạy firebase projects:addfirebase báo **403 PERMISSION_DENIED**, nhưng gcloud projects describe vẫn thành công.

**Đáp án:** Có quyền đọc metadata **không đồng nghĩa** có quyền Firebase project update/enable APIs. Kiểm tra IAM permissions **firebase.projects.update, resourcemanager.projects.get, serviceusage.services.enable/get**, Firebase Terms và organization policies.

### Bài tập I — Data residency

Đội đặt project display name “Shop Vietnam”, rồi cho rằng Firestore và Google Analytics sẽ tự lưu dữ liệu tại Việt Nam.

**Đáp án:** Sai. Project display name không định vị dữ liệu. Chọn **Firestore database location, Storage bucket region, Analytics reporting location** theo sản phẩm và vùng được hỗ trợ; đánh giá latency, egress, residency và điều kiện thay đổi location.

### Bài tập J — Xóa ứng dụng

Team muốn ngừng một Android app không còn người dùng. Có người đề xuất **Delete Firebase project**.

**Đáp án:** Sai phạm vi. Firebase project chính là Google Cloud project, xóa sẽ tác động toàn bộ tài nguyên. Đánh giá gỡ **Firebase App registration** và cleanup các tài nguyên liên quan theo kế hoạch mà không xóa backend chung. Có backup và xác minh dependency trước mọi thao tác destructive.

## 17. Tổng kết và tài liệu tham khảo

**Sáu điều cần nhớ:**

1. **Firebase project = Google Cloud project đã bật cấu hình Firebase**, với **chung project ID/number, IAM, billing và organization hierarchy**.
2. **Firebase Apps** là các client registrations bên trong project; thêm app **không** tạo môi trường database/billing riêng.
3. Thêm Firebase vào project hiện có **không tạo project mới**, có thể bật APIs/service identities, và **không có thao tác gỡ hoàn toàn được hỗ trợ**.
4. **Firebase Security Rules** áp dụng cho client SDK, còn **Java/server Admin SDK dùng IAM**; hai lớp không thay thế nhau.
5. Project đã liên kết Cloud Billing dùng Firebase **Blaze**; kiểm soát phí theo từng sản phẩm, không dựa vào tên gói hay budget alert như một hard cap.
6. Tách **dev/staging/prod bằng projects**, chọn đúng Firebase app config, service identity, Firestore location và kiểm tra dữ liệu/chi phí trước khi deploy hoặc xóa.

**Tài liệu chính thức:**

1. [Understand Firebase projects](https://firebase.google.com/docs/projects/learn-more) — cấu trúc, IDs, apps và resource hierarchy.
2. [Use Firebase with an existing Google Cloud project](https://firebase.google.com/docs/projects/use-firebase-with-existing-cloud-project) — thao tác Add Firebase, IAM prerequisites và những thay đổi không thể hoàn tác hoàn toàn.
3. [Firebase project management REST API](https://firebase.google.com/docs/reference/firebase-management/rest/v1beta1/projects) — projects.addFirebase và mapping identifiers.
4. [Firebase CLI reference](https://firebase.google.com/docs/cli) — projects:addfirebase, projects:create, aliases, apps:list.
5. [Firebase project IAM](https://firebase.google.com/docs/projects/iam/overview) — roles, principals và Google Cloud IAM console.
6. [Firebase pricing plans](https://firebase.google.com/docs/projects/billing/firebase-pricing-plans) — Spark, Blaze và Cloud Billing.
7. [Configure multiple Firebase projects](https://firebase.google.com/docs/projects/multiprojects) — dev/prod, SDK config, build variants.
8. [Firebase API keys](https://firebase.google.com/docs/projects/api-keys) — API key restrictions và mô hình config public.
9. [Get started with Cloud Firestore Security Rules](https://firebase.google.com/docs/firestore/security/get-started) — client rules và server IAM.
10. [Firebase Admin SDK setup](https://firebase.google.com/docs/admin/setup) — Java/ADC/Cloud Run.
11. [Firestore server client quickstart](https://firebase.google.com/docs/firestore/quickstart-server) — Java Firestore SDK.
12. [Firebase project setup best practices](https://firebase.google.com/docs/projects/dev-workflows/general-best-practices) — môi trường, apps và ranh giới dữ liệu.
