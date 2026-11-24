# Kiểm tra định dạng reachability metadata và các build flag theo phiên bản

> **Chương:** Di chuyển và nâng cấp  
> **Module:** SPRING_BOOT_NATIVE_IMAGE  
> **Mục tiêu:** Nhận diện định dạng reachability metadata theo GraalVM JDK; chuyển cấu hình JSON cũ sang định dạng hợp nhất; quản lý metadata từ ứng dụng và thư viện; kiểm tra build flags, Native Build Tools và Spring Boot AOT trước khi nâng cấp toolchain.

## 1. Vì sao cần kiểm tra metadata và build flags khi nâng cấp?

Spring Boot Native Image phụ thuộc vào nhiều thành phần cùng tham gia build: Spring Boot plugin, Spring Framework, GraalVM JDK/Native Image, Native Build Tools và reachability metadata của thư viện. Mỗi thành phần có vòng đời phiên bản riêng. Một cấu hình từng build thành công có thể phát cảnh báo, bị bỏ qua hoặc không còn hợp lệ khi nâng GraalVM.

Nguyên nhân thường gặp:

- File metadata được tạo bởi Tracing Agent của JDK cũ có cấu trúc khác định dạng mà JDK mới khuyến nghị.
- Điều kiện metadata dùng `typeReachable` trong khi phiên bản mới dùng `typeReached`.
- Resource pattern được viết theo regular expression nhưng được chuyển nguyên xi sang trường glob.
- Proxy hoặc serialization metadata vẫn nằm trong file riêng dù định dạng mới đưa chúng vào reflection metadata.
- Build script giữ các flag đã deprecated hoặc bị loại bỏ.
- Một flag hợp lệ ở `native-image` CLI lại được truyền nhầm cho JVM chạy Maven/Gradle.
- Plugin tải reachability metadata cho dependency nhưng repository release hoặc metadata version của một thư viện bị pin không phù hợp.

Một lần nâng cấp cần kiểm tra cả **cấu trúc metadata**, **ý nghĩa của từng entry**, **các flag mà builder hỗ trợ** và **cách plugin chuyển flag tới builder**. Chỉ đổi tên file hoặc nâng version plugin không chứng minh native executable đã giữ đủ hành vi động.

## 2. Phân biệt các phiên bản tham gia native build

Không có một con số duy nhất đại diện cho toàn bộ toolchain. Hãy ghi riêng các thành phần sau:

| Thành phần | Vai trò | Cần ghi lại |
|---|---|---|
| Spring Boot | Điều phối AOT, native packaging và dependency management | Phiên bản Boot và Java baseline |
| Spring Framework / Spring Data | Sinh AOT contributions và runtime hints | Phiên bản được Boot BOM quản lý |
| GraalVM JDK / Native Image | Phân tích tĩnh, đọc metadata và tạo executable | JDK major, GraalVM distribution, native-image --version |
| GraalVM Native Build Tools | Maven/Gradle integration, test và metadata repository | Phiên bản plugin |
| GraalVM Reachability Metadata Repository | Metadata cho thư viện bên thứ ba | Repository release và metadata version của từng thư viện khi có override |
| Buildpacks / builder image | Đóng gói và chọn Native Image toolchain | Builder/run image digest và Java version |

Một số nguyên tắc khi chọn phiên bản:

1. Chọn Spring Boot và Java baseline trước; dùng BOM của Spring Boot để quản lý Spring Framework, Spring Data và các dependency liên quan.
2. Chọn GraalVM distribution có JDK major phù hợp với Java version mà Spring Boot/build pipeline hỗ trợ.
3. Chọn Native Build Tools tương thích với Gradle/Maven wrapper và GraalVM JDK đang dùng.
4. Ghi nhận reachability metadata repository release được plugin sử dụng; kiểm tra metadata có cho đúng version của thư viện hay không.
5. Khóa các version trong CI để hai lần build không âm thầm dùng builder image hoặc metadata repository khác nhau.

Không suy luận tương thích chỉ từ việc các thành phần đều hỗ trợ cùng một Java language level. Buildpacks, Native Image và plugin có thể có yêu cầu riêng. Tài liệu Spring Boot hiện hành cũng yêu cầu kiểm tra Java version dùng để biên dịch khi build native image bằng Buildpacks. [Spring Boot — Developing a Native Application](https://docs.spring.io/spring-boot/how-to/native-image/developing-your-first-application.html)

## 3. Định dạng metadata cũ: nhiều file theo từng tính năng

Ở các GraalVM JDK đời cũ, metadata được chia thành các file riêng trong classpath, thường đặt dưới:

```text
src/main/resources/
└── META-INF/
    └── native-image/
        └── com.example/
            └── payment-service/
                ├── reflect-config.json
                ├── resource-config.json
                ├── proxy-config.json
                ├── serialization-config.json
                └── jni-config.json
```

Các file này có schema khác nhau:

| File cũ | Nội dung |
|---|---|
| `reflect-config.json` | Class, constructor, method, field cần reflection |
| `resource-config.json` | Resource include/exclude và resource bundles |
| `proxy-config.json` | Danh sách interface theo thứ tự để tạo JDK dynamic proxy |
| `serialization-config.json` | Các type được Java serialization sử dụng |
| `jni-config.json` | Class/member mà native code truy cập qua JNI |

Ví dụ `reflect-config.json` theo schema cũ:

```json
[
  {
    "condition": {
      "typeReachable": "com.example.payment.PaymentService"
    },
    "name": "com.example.payment.dto.PaymentCommand",
    "allDeclaredConstructors": true,
    "methods": [
      {
        "name": "from",
        "parameterTypes": ["java.lang.String"]
      }
    ]
  }
]
```

Một số đặc điểm dễ nhận ra:

- File reflection thường là một JSON array.
- Tên class nằm trong trường `name`.
- Điều kiện reachability dùng `condition.typeReachable`.
- Resource metadata có object `resources` với `includes`/`excludes`, mỗi entry dùng `pattern`.
- Proxy và serialization có file riêng.

Ví dụ resource metadata cũ:

```json
{
  "resources": {
    "includes": [
      {
        "condition": {
          "typeReachable": "com.example.payment.ReportService"
        },
        "pattern": "db/migration/.*\\.sql"
      }
    ]
  },
  "bundles": [
    {
      "name": "com.example.payment.Messages",
      "locales": ["en", "vi"]
    }
  ]
}
```

Trong cấu trúc này, `pattern` là regular expression. Không được đổi tên trường thành `glob` rồi giữ nguyên biểu thức regex, vì hai cách biểu diễn có ngữ nghĩa khác nhau.

## 4. Định dạng hợp nhất từ GraalVM JDK 23

GraalVM for JDK 23 giới thiệu định dạng hợp nhất `reachability-metadata.json`. Các file riêng như `reflect-config.json`, `resource-config.json`, `proxy-config.json`, `serialization-config.json` và `jni-config.json` được đánh dấu deprecated, nhưng vẫn được Native Image chấp nhận để hỗ trợ tương thích ngược. [GraalVM JDK 23 Release Notes](https://www.graalvm.org/release-notes/JDK_23/)

Đường dẫn khuyến nghị:

```text
src/main/resources/
└── META-INF/
    └── native-image/
        └── com.example/
            └── payment-service/
                └── reachability-metadata.json
```

Định dạng mới dùng một JSON object cấp cao nhất. Các nhóm metadata phổ biến gồm:

- `reflection`: reflection, dynamic proxy và các khai báo serialization theo schema mới.
- `jni`: type/member mà native code truy cập.
- `resources`: resource trên classpath/module path.
- `bundles`: resource bundles phục vụ localization.

Ví dụ tổng hợp:

```json
{
  "reflection": [],
  "jni": [],
  "resources": [],
  "bundles": []
}
```

Không phải mọi project đều cần đủ các nhóm trên. Chỉ khai báo nhóm metadata mà ứng dụng hoặc dependency thực sự sử dụng. Ngoài ra, `predefined-classes-config.json` vẫn là cấu hình riêng cho predefined classes; không gộp file này vào `reachability-metadata.json`.

Native Image đọc metadata từ các classpath entries dưới `META-INF/native-image/<groupId>/<artifactId>/`. Một dependency có thể đóng gói metadata của chính nó; ứng dụng cũng có thể cung cấp metadata riêng trong artifact. [GraalVM JDK 25 — Reachability Metadata](https://www.graalvm.org/jdk25/reference-manual/native-image/metadata/)

## 5. Những thay đổi cấu trúc cần xử lý khi chuyển đổi

### 5.1. Reflection: `name` thành `type`

Ví dụ cũ:

```json
[
  {
    "name": "com.example.PaymentCommand",
    "allDeclaredConstructors": true
  }
]
```

Dạng hợp nhất:

```json
{
  "reflection": [
    {
      "type": "com.example.PaymentCommand",
      "allDeclaredConstructors": true
    }
  ]
}
```

Trường `type` cũng hỗ trợ mô tả proxy hoặc lambda type theo schema mới. Khi chuyển đổi, kiểm tra các thuộc tính như constructors, methods, fields, query-only access và unsafe allocation có được giữ đúng hay không. Không thay tên trường một cách máy móc rồi bỏ sót các member cụ thể mà ứng dụng cần.

### 5.2. Điều kiện: `typeReachable` thành `typeReached`

GraalVM JDK 23 thay `typeReachable` bằng `typeReached`. Điều kiện mới xét type đã được xem là reached tại runtime; type được xem là reached ngay trước khi class initialization của type bắt đầu, hoặc khi một subtype của nó được reach. [GraalVM JDK 23 Release Notes](https://www.graalvm.org/release-notes/JDK_23/)

Ví dụ dạng mới:

```json
{
  "reflection": [
    {
      "condition": {
        "typeReached": "com.example.payment.PaymentService"
      },
      "type": "com.example.payment.dto.PaymentCommand",
      "allDeclaredConstructors": true
    }
  ]
}
```

Đừng chỉ tìm và thay chuỗi trong toàn bộ repository mà không đọc lại ý nghĩa điều kiện. Metadata có điều kiện chỉ có hiệu lực khi condition type được reach. Nếu chọn nhầm condition class, một entry hợp lệ về cú pháp vẫn có thể không được áp dụng ở runtime.

### 5.3. Resource: object `includes`/`excludes` thành danh sách entry

Dạng mới đưa resource entry vào mảng `resources`:

```json
{
  "resources": [
    {
      "glob": "db/migration/*.sql"
    },
    {
      "glob": "reports/templates/**"
    }
  ]
}
```

GraalVM JDK 23 bổ sung hỗ trợ glob cho resource path và Tracing Agent bắt đầu xuất entry theo glob format. Glob hỗ trợ `*` trong một path level và `**` xuyên qua nhiều level. [GraalVM JDK 23 Release Notes](https://www.graalvm.org/release-notes/JDK_23/)

Ví dụ chuyển đổi:

| Regex cũ (pattern) | Glob mới (glob) |
|---|---|
| db/migration/.*\\.sql | db/migration/*.sql |
| reports/.* | reports/** |
| config/application\\.ya?ml | Viết hai glob cụ thể: config/application.yaml, config/application.yml |

Bảng chỉ minh họa các pattern đơn giản. Với regex phức tạp, hãy viết lại theo glob semantics hoặc giữ cấu hình legacy trong giai đoạn chuyển tiếp nếu phiên bản Native Image mục tiêu còn hỗ trợ. Kiểm tra resource thực tế trong executable sau khi build.

## 6. Chuyển đổi proxy, serialization và JNI metadata

### 6.1. Dynamic proxy

Trong định dạng cũ, proxy interfaces nằm trong `proxy-config.json`:

```json
[
  {
    "interfaces": [
      "com.example.payment.PaymentGateway",
      "java.io.Serializable"
    ]
  }
]
```

Từ định dạng hợp nhất, proxy type được khai báo trong phần `reflection`:

```json
{
  "reflection": [
    {
      "type": {
        "proxy": [
          "com.example.payment.PaymentGateway",
          "java.io.Serializable"
        ]
      }
    }
  ]
}
```

Thứ tự interface là một phần của định nghĩa proxy. Không sắp xếp lại danh sách hoặc gộp hai proxy chỉ vì chúng dùng cùng các interface nhưng thứ tự khác nhau. GraalVM JDK 23 đánh dấu `proxy-config.json` deprecated và vẫn hỗ trợ để tương thích ngược. [GraalVM JDK 23 Release Notes](https://www.graalvm.org/release-notes/JDK_23/)

### 6.2. Serialization

Ở GraalVM JDK cũ, serialization có file `serialization-config.json` riêng với danh sách `types`. Từ GraalVM JDK 24, serialization JSON metadata được đưa vào reflection metadata bằng thuộc tính `serializable`.

Ví dụ dạng mới:

```json
{
  "reflection": [
    {
      "type": "com.example.payment.PaymentEvent",
      "serializable": true
    }
  ]
}
```

Khi chuyển đổi, xác nhận cả type được serialize và deserialize, các lớp con có thể xuất hiện trong object graph, proxy serialization và custom serialization hooks. Không đăng ký tất cả class trong package chỉ để làm mất lỗi. Serialization metadata rộng có thể làm executable lớn hơn và mở rộng bề mặt dữ liệu được phép deserialize. [GraalVM JDK 24 Release Notes](https://www.graalvm.org/release-notes/JDK_24/)

### 6.3. JNI

Metadata JNI cũ nằm trong `jni-config.json`; định dạng hợp nhất chuyển các entry sang mảng `jni`. Trường `type` và các member được giữ tương ứng với nhu cầu lookup từ native code.

Ví dụ:

```json
{
  "jni": [
    {
      "type": "com.example.payment.NativeBridge",
      "methods": [
        {
          "name": "onPaymentResult",
          "parameterTypes": ["java.lang.String", "int"]
        }
      ]
    }
  ]
}
```

JNI metadata khác reflection metadata ở nguồn truy cập: native code gọi vào Java qua JNI. Nếu thư viện dùng JNI, hãy kiểm tra cả class, method và field được native library lookup. Test JVM không đủ để xác nhận đường JNI hoạt động trong native executable.

## 7. Bảng mốc thay đổi theo GraalVM JDK

Bảng dưới đây tóm tắt những mốc ảnh hưởng trực tiếp tới việc chuyển đổi metadata và build arguments. Đây là mốc tính năng của Native Image; hãy kiểm tra release cụ thể của distribution mà dự án đang cài.

| GraalVM JDK | Metadata và build behavior cần chú ý |
|---|---|
| JDK 17 / 21 | Dạng split files là cấu hình thường gặp: `reflect-config.json`, `resource-config.json`, `proxy-config.json`, `serialization-config.json`, `jni-config.json`. Reflection dùng `name`, condition dùng `typeReachable`; resource dùng `pattern` regex. |
| JDK 22 | Vẫn có thể gặp split metadata. Strict image heap được bật mặc định; không cần sao chép các cấu hình lịch sử chỉ để bật lại chế độ mặc định này. |
| JDK 23 | Giới thiệu `reachability-metadata.json`; thay `typeReachable` bằng `typeReached`; proxy metadata chuyển vào reflection type; hỗ trợ glob resource; `--exact-reachability-metadata` xuất hiện; `--report-unsupported-elements-at-runtime` deprecated và runtime reporting được bật mặc định. |
| JDK 24 | Serialization metadata được tích hợp vào reflection entries bằng `serializable`; một số trường serialization cũ như `customTargetConstructorClass` bị loại bỏ. Prefix `-Dgraal.` bắt đầu phát deprecation warning; chuyển sang `-Djdk.graal.` cho Graal compiler options tương ứng. |
| JDK 25 | Tài liệu Native Image đánh dấu `--enable-http`, `--enable-https` và `--enable-url-protocols` deprecated; với URL protocol handler, dùng reachability metadata. Các option có thể khác giữa JDK 25.0 và các bản cập nhật 25.x. |

Các nguồn release notes: [JDK 22](https://www.graalvm.org/release-notes/JDK_22/), [JDK 23](https://www.graalvm.org/release-notes/JDK_23/), [JDK 24](https://www.graalvm.org/release-notes/JDK_24/), [JDK 25 Native Image options](https://www.graalvm.org/jdk25/reference-manual/native-image/overview/Options/).

Đừng hiểu bảng này là ma trận hỗ trợ của Spring Boot. Nó mô tả thay đổi của GraalVM Native Image. Spring Boot release và Java baseline vẫn là điều kiện riêng phải kiểm tra.

## 8. Các build flag chẩn đoán missing registration theo phiên bản

Một khác biệt quan trọng khi nâng từ JDK 21/22 lên JDK 23+ là cách bật exact reachability metadata và báo lỗi registration bị thiếu.

### 8.1. GraalVM JDK 23 trở lên

Flag build-time:

```text
--exact-reachability-metadata
```

Có thể giới hạn cho package cụ thể khi đang chuyển đổi từng phần:

```text
--exact-reachability-metadata=com.example.payment,com.example.integration
```

Khi chạy native executable trong test, dùng:

```bash
./target/payment-service -XX:MissingRegistrationReportingMode=Warn
```

`Warn` giúp tìm các điểm thiếu registration mà chưa buộc ứng dụng dừng ngay. Trong test nghiêm ngặt, có thể dùng `Exit` để process thoát ngay khi gặp lỗi registration, kể cả trường hợp code bắt `Throwable` và vô tình nuốt lỗi:

```bash
./target/payment-service -XX:MissingRegistrationReportingMode=Exit
```

Exact metadata mode giúp lỗi reflection, resources, JNI và serialization xuất hiện sớm hơn, dễ truy ngược hơn. Nên bật trên CI/native test trước khi nâng cấp major toolchain, sau đó xử lý từng entry bị thiếu. [GraalVM — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/)

### 8.2. GraalVM JDK 22 trở xuống

Các flag mới `--exact-reachability-metadata` và `-XX:MissingRegistrationReportingMode` không phải lựa chọn tương thích cho mọi bản GraalVM cũ. Native Build Tools hướng dẫn dùng các hosted option ở build time:

```text
-H:ThrowMissingRegistrationErrors=
-H:MissingRegistrationReportingMode=Warn
```

Đặt các option này trong cấu hình native build của phiên bản cũ. Đừng copy lệnh chạy JDK 23+ vào executable được build bằng JDK 21/22 rồi giả định runtime hiểu các option đó.

Tài liệu Native Build Tools ghi rõ `--exact-reachability-metadata` được giới thiệu từ GraalVM JDK 23; với phiên bản cũ, dùng `-H:ThrowMissingRegistrationErrors=`. Với GraalVM cũ hơn JDK 23, `-H:MissingRegistrationReportingMode=Warn` được truyền khi build. [Native Build Tools — Troubleshoot Missing Configuration](https://graalvm.github.io/native-build-tools/latest/end-to-end-maven-guide.html)

### 8.3. Không nhầm missing registration với unsupported elements

`--report-unsupported-elements-at-runtime` là flag cũ để chuyển một số lỗi unsupported element từ build sang runtime. GraalVM JDK 23 đánh dấu flag này deprecated và bật runtime reporting mặc định.

Flag đó không thay thế metadata. Nếu ứng dụng gọi reflection mà thiếu registration, hãy bổ sung đúng metadata hoặc sửa code để static analysis nhìn thấy đường truy cập. Không thêm flag unsupported-runtime như một cách chữa lỗi reflection/resource.

## 9. URL protocol flags và metadata trong JDK mới

Trước đây, project có thể thêm:

```text
--enable-http
--enable-https
--enable-url-protocols=http,https
```

Trong tài liệu Native Image JDK 25, các option trên được đánh dấu deprecated. Thay vào đó, nếu ứng dụng thực sự dùng `java.net.URL` với handler HTTP/HTTPS, đăng ký constructor của handler trong `reachability-metadata.json`:

```json
{
  "reflection": [
    {
      "type": "sun.net.www.protocol.http.Handler",
      "methods": [
        {
          "name": "<init>",
          "parameterTypes": []
        }
      ]
    },
    {
      "type": "sun.net.www.protocol.https.Handler",
      "methods": [
        {
          "name": "<init>",
          "parameterTypes": []
        }
      ]
    }
  ]
}
```

Đây là metadata cho URL protocol handler của JDK. Nó không phải flag tổng quát để bật HTTP server, Spring MVC, WebFlux hoặc mọi HTTP client. Những stack đó có cơ chế reachability riêng từ framework/dependency và cần được kiểm tra theo thư viện đang sử dụng. [GraalVM — URL Protocols in Native Image](https://www.graalvm.org/latest/reference-manual/native-image/dynamic-features/URLProtocols/)

## 10. Phân loại build flags trước khi di chuyển

Không phải mọi option có dấu gạch ngang đều được truyền ở cùng giai đoạn. GraalVM phân loại option theo nơi nó tác động:

| Cú pháp | Ý nghĩa | Ví dụ |
|---|---|---|
| `--...` | Native Image build option | `--exact-reachability-metadata` |
| `-H:` | Hosted option, cấu hình quá trình build hoặc mặc định runtime được ghi vào image | `-H:IncludeLocales=vi,en` |
| `-R:` | Thiết lập giá trị ban đầu cho runtime option khi build | Tùy option và phiên bản |
| `-XX:` | Runtime option khi khởi chạy native executable | `-XX:MissingRegistrationReportingMode=Warn` |
| `-Dname=value` | System property được đặt cho Native Image build; một số JDK property được capture vào executable | `-Duser.language=vi` |
| `-J...` | Chuyển option cho JVM chạy tiến trình Native Image builder | `-J-Xmx8g` |

`-H:` và `-R:` không phải hai cách viết thay thế tùy ý. Đọc loại option trong tài liệu đúng JDK trước khi chuyển nó giữa build script và command line. `-D` cũng không mặc nhiên có nghĩa property sẽ được đọc lại ở runtime; property thường chỉ tồn tại trong build process, ngoại trừ các JDK property được Native Image giữ theo quy tắc của phiên bản.

Trước khi nâng cấp, lấy danh sách option từ chính builder được CI sử dụng:

```bash
native-image --version
native-image --help
native-image --help-extra
native-image --expert-options
```

Các bản mới có thể hỗ trợ `--print-options` để xuất danh sách có cấu trúc, ví dụ JSON. Chỉ dùng lệnh này khi `--help` của bản đang cài xác nhận nó có sẵn. Option không được nhận diện sẽ làm build thất bại; không nên dựa vào danh sách trên một trang tài liệu của JDK khác. [GraalVM JDK 25 — Command-line Options](https://www.graalvm.org/jdk25/reference-manual/native-image/overview/Options/)

## 11. Những build flag cần rà soát khi nâng cấp

### 11.1. Class initialization

Hai option hiện hành để điều khiển thời điểm khởi tạo class là:

```text
--initialize-at-build-time=com.example.StableMetadata
--initialize-at-run-time=com.example.RuntimeConfiguration
```

Chỉ định class hoặc package thật sự cần thiết. Khởi tạo ở build time có thể capture state từ môi trường build vào executable; khởi tạo ở runtime giữ quyết định đó cho lúc ứng dụng chạy. Không sao chép một danh sách package lớn từ dự án cũ mà không kiểm tra static initializer, file, clock, random seed, environment variables và security providers.

### 11.2. Strict image heap và class initialization cũ

GraalVM JDK 22 đã bật strict image heap theo mặc định. Khi nâng lên JDK 23, không mang theo flag lịch sử `--StrictImageHeap` với kỳ vọng nó tiếp tục thay đổi hành vi; release notes JDK 23 ghi nhận option cũ này không còn tác dụng. Hãy dùng các option class initialization hiện hành và sửa warning theo hướng dẫn của builder.

### 11.3. Unsupported elements

`--report-unsupported-elements-at-runtime` bị deprecated từ GraalVM JDK 23 vì runtime reporting đã được bật mặc định. Xóa flag cũ sau khi xác nhận không có script hoặc profile nào phụ thuộc vào hành vi khác của phiên bản trước.

### 11.4. Graal compiler system properties

Nếu build script có các property dạng `-Dgraal.SomeOption=...`, hãy kiểm tra lại. GraalVM JDK 24 bắt đầu phát deprecation warning cho prefix `graal.` và khuyến nghị dùng `jdk.graal.` cho Graal compiler options tương ứng. Thay đổi này áp dụng cho property của Graal compiler; không đổi mọi Java system property bắt đầu bằng `-D`.

### 11.5. Optimization level và build report

GraalVM JDK 23 bổ sung `-Os` để ưu tiên kích thước executable. Không truyền `-Os` vào builder cũ chưa hỗ trợ. Đánh giá size, startup và throughput trên workload thực tế trước khi chọn optimization level.

Có thể yêu cầu build report bằng `--emit build-report` để xem nội dung image và dynamic access. Tính năng Build Report không có trong GraalVM Community Edition theo tài liệu hiện hành; với bản phân phối không hỗ trợ, dùng log, metadata report và các công cụ kiểm tra resource khác. [GraalVM — Native Image Build Report](https://www.graalvm.org/latest/reference-manual/native-image/overview/build-report/)

## 12. Đặt cấu hình mặc định trong `native-image.properties`

Nếu một thư viện hoặc ứng dụng cần các option ổn định mỗi lần build, đặt file `native-image.properties` cùng namespace metadata:

```text
src/main/resources/
└── META-INF/
    └── native-image/
        └── com.example/
            └── payment-service/
                ├── native-image.properties
                └── reachability-metadata.json
```

Ví dụ:

```properties
Args = --exact-reachability-metadata
ImageName = payment-service
```

`Args` chứa các option được chuyển tới Native Image builder. `JavaArgs` dành cho JVM chạy builder; `ImageName` đặt tên executable mặc định. Có thể tham chiếu argument file bằng cú pháp `@file` khi cấu hình dài, nhưng file đó phải nằm trong classpath entry chứa `native-image.properties` theo quy tắc của Native Image.

Các option được đánh giá từ trái sang phải. Option truyền sau trên command line có thể ghi đè cấu hình trong file. Tránh khai báo cùng một flag ở `native-image.properties`, Maven/Gradle và Buildpacks với giá trị khác nhau; khi đó rất khó xác định giá trị cuối cùng builder nhận được. [GraalVM — Native Image Build Configuration](https://www.graalvm.org/jdk25.5/reference-manual/native-image/overview/BuildConfiguration/)

## 13. Cấu hình flags với Maven và Gradle

### 13.1. Maven Native Build Tools

Có thể truyền build arguments qua `native-maven-plugin`:

```xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>--exact-reachability-metadata</buildArg>
            <buildArg>--emit build-report</buildArg>
        </buildArgs>
    </configuration>
</plugin>
```

Mỗi `buildArg` là một Native Image option expression, không phải toàn bộ shell command. Nếu một option có giá trị gồm nhiều token, giữ chúng trong cùng expression theo cách plugin yêu cầu. Nếu chạy GraalVM Community Edition không hỗ trợ Build Report, bỏ dòng `--emit build-report`.

Khi dùng `spring-boot-starter-parent`, profile `native` của Spring Boot Maven plugin có thể cấu hình `process-aot`, các thiết lập native build và tải third-party reachability metadata. Nếu không dùng parent này, phải tự cấu hình `process-aot` và các bước metadata cần thiết. [Spring Boot — Maven AOT Processing](https://docs.spring.io/spring-boot/maven-plugin/aot.html)

### 13.2. Gradle Native Build Tools

Với Gradle Groovy DSL:

```groovy
graalvmNative {
    binaries {
        main {
            buildArgs.add("--exact-reachability-metadata")
            buildArgs.add("--emit=build-report")
        }
    }
}
```

Nếu dùng Kotlin DSL, dùng API tương ứng của phiên bản plugin đang khóa trong build. Đừng sao chép cú pháp Groovy sang `build.gradle.kts` mà không chuyển đúng kiểu và accessor.

Spring Boot Gradle plugin phối hợp AOT tasks khi GraalVM Native plugin được áp dụng. Xác nhận task AOT và native compile xuất hiện trong task graph; không chỉ nhìn thấy plugin trong `plugins` block rồi kết luận nó đã chạy.

### 13.3. Không trộn build option và runtime argument

Ví dụ:

- `--exact-reachability-metadata` là build option.
- `-XX:MissingRegistrationReportingMode=Warn` là runtime option của native executable trên GraalVM JDK 23+.
- `-J-Xmx8g` điều chỉnh JVM chạy builder, không đặt heap cho ứng dụng native.

Đặt từng option vào đúng nơi trong plugin. Nếu runtime argument bị đặt trong `buildArgs`, hoặc builder JVM option bị truyền cho executable, build có thể thất bại hoặc không có tác dụng như mong muốn.

## 14. Reachability Metadata Repository cho thư viện bên thứ ba

Native Build Tools có thể tự tìm metadata cho dependency từ GraalVM Reachability Metadata Repository. Repository chứa cấu hình do thư viện hoặc cộng đồng đóng góp cho những dependency chưa tự đóng gói đủ metadata.

Với Maven, plugin hỗ trợ metadata repository và có thể tải cấu hình phù hợp với dependency. Spring Boot `native` profile cũng cấu hình việc tải third-party reachability metadata. Với Gradle, plugin `org.graalvm.buildtools.native` cung cấp cấu hình `graalvmNative.metadataRepository`.

Có hai khái niệm version phải tách riêng:

1. **Repository release version:** phiên bản gói metadata repository mà Native Build Tools tải.
2. **Per-module metadata version:** phiên bản metadata được chọn cho một dependency cụ thể khi repository có nhiều biến thể hoặc không có metadata đúng phiên bản thư viện.

Ví dụ Maven override metadata version của một dependency:

```xml
<metadataRepository>
    <enabled>true</enabled>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>legacy-client</artifactId>
            <metadataVersion>2</metadataVersion>
        </dependency>
    </dependencies>
</metadataRepository>
```

Ví dụ Gradle override cho module cụ thể:

```groovy
graalvmNative {
    metadataRepository {
        moduleToConfigVersion.put("com.example:legacy-client", "2")
    }
}
```

Con số `2` trong ví dụ là metadata version của module, không phải GraalVM JDK major, Spring Boot version hay Native Build Tools plugin version. Chỉ override khi đã xác minh metadata đó tương thích với dependency đang dùng. [Native Build Tools — Maven Metadata Repository](https://graalvm.github.io/native-build-tools/latest/maven-plugin.html), [Gradle Metadata Repository](https://graalvm.github.io/native-build-tools/latest/gradle-plugin)

### 14.1. Kiểm tra dependency chưa có metadata

Với Maven:

```bash
./mvnw native:list-libraries-missing-metadata
```

Với Gradle:

```bash
./gradlew listLibrariesMissingMetadata
```

Các goal/task này quét dependency runtime trực tiếp và báo những thư viện chưa được repository hỗ trợ. Hãy kiểm tra báo cáo trước khi tự viết metadata cho một thư viện đã có cấu hình chính thức. Nếu thiếu metadata, đọc issue/release note của thư viện và xác định version nào đã được kiểm thử.

### 14.2. Khi nào cần đóng gói repository metadata vào JAR?

Mặc định Native Build Tools có thể dùng metadata repository trong lúc native build. Nếu một bước khác sẽ nhận JAR AOT-processed và chuyển nó thành native image sau đó, metadata repository cần được copy vào artifact.

Với Maven, dùng goal `add-reachability-metadata` trong execution phù hợp. Với Gradle, dùng task `collectReachabilityMetadata` và đưa output vào JAR nếu pipeline downstream cần metadata nằm trong artifact. Không cần thêm bước copy này nếu native image được tạo ngay trong cùng build và plugin đã resolve metadata cho builder.

## 15. Thu thập metadata bằng Tracing Agent

Tracing Agent quan sát các thao tác động khi ứng dụng chạy trên JVM và ghi lại metadata cho reflection, resource, proxy, serialization hoặc JNI mà nó nhìn thấy. Đây là cách hữu ích để tìm entry còn thiếu khi thư viện chưa cung cấp metadata phù hợp.

Ví dụ chạy Spring Boot executable JAR đã có AOT assets:

```bash
java -Dspring.aot.enabled=true \
  -agentlib:native-image-agent=config-output-dir=target/native-agent \
  -jar target/payment-service.jar
```

Sau khi ứng dụng khởi động, thực hiện các luồng nghiệp vụ cần kiểm tra: deserialize request, đọc mapping/resource, chạy repository query, tạo proxy, gọi JNI hoặc serialize message. Dừng ứng dụng bình thường để Agent ghi file output.

### 15.1. Kiểm tra output theo GraalVM version

- Với GraalVM JDK cũ, Agent có thể tạo các file split như `reflect-config.json`, `resource-config.json` và `proxy-config.json`.
- Với GraalVM JDK 23+, Agent có thể tạo `reachability-metadata.json` theo định dạng hợp nhất.
- Không trộn output được tạo từ nhiều GraalVM major versions mà không chuẩn hóa và kiểm tra schema.
- Không ghi đè metadata đã được review bằng output Agent mới trước khi so sánh diff.

Agent chỉ ghi nhận đường đi đã được thực thi. Nếu test chưa gọi tới một nhánh reflection hoặc resource, metadata tương ứng có thể không xuất hiện. Hãy dùng integration tests có độ bao phủ phù hợp và kiểm tra các đường lỗi, cấu hình thay thế, profile và payload thực tế.

### 15.2. Lọc metadata do test tạo ra

Nếu chạy Agent trong test process, output có thể chứa metadata của JUnit, Maven Surefire, test fixtures hoặc framework test. Không đưa toàn bộ metadata đó vào production image theo mặc định.

Hãy:

1. Xác định entry thuộc application/runtime dependency hay chỉ thuộc test framework.
2. Giữ các constructor/member/resource thật sự được truy cập động.
3. Dùng condition khi phù hợp để metadata chỉ có hiệu lực khi type liên quan được reach.
4. So sánh output Agent với metadata repository mà dependency đã cung cấp.
5. Chạy native tests sau khi lọc để xác nhận không xóa nhầm entry cần thiết.

Tracing Agent là công cụ thu thập bằng chứng từ runtime; output của nó cần được review như code/configuration trước khi commit.

## 16. Quy trình nâng cấp metadata và build flags

Thực hiện nâng cấp theo từng bước để xác định thay đổi nào làm build hoặc runtime khác đi:

1. **Chụp baseline:** ghi Spring Boot, Java, GraalVM, Native Build Tools, metadata repository, dependency tree, build arguments và kết quả native tests hiện tại.
2. **Chốt target JDK:** xác nhận GraalVM JDK major và Spring Boot release hỗ trợ nhau; kiểm tra `native-image --version`.
3. **Kiểm tra dependency metadata:** chạy `native:list-libraries-missing-metadata` hoặc `listLibrariesMissingMetadata`; xử lý dependency chưa được hỗ trợ.
4. **Kiểm tra cấu hình cũ:** liệt kê tất cả split metadata files, `native-image.properties`, Maven `buildArgs`, Gradle `buildArgs`, Buildpacks arguments và environment variables dùng trong build.
5. **Chọn schema theo target:** với JDK 23+, chuyển sang `reachability-metadata.json`; với target cũ hơn, giữ schema mà builder đó hỗ trợ. Không dùng schema JDK 25 để validate project vẫn build bằng JDK 21.
6. **Chuyển entry:** cập nhật `name`/`type`, `typeReachable`/`typeReached`, resource regex/glob, proxy và serialization theo đúng schema. Kiểm tra điều kiện và thứ tự interface.
7. **Rà soát flags:** bỏ option deprecated, thay missing-registration diagnostics theo JDK major, xác nhận mọi option còn tồn tại trong `native-image --help`.
8. **Chạy Spring AOT:** xác nhận `process-aot` hoàn tất với đúng profile và environment build-time; kiểm tra generated sources, classes và JSON hints.
9. **Build native:** chạy Maven/Gradle/Buildpacks với toolchain đã khóa. Lưu log đầy đủ và native image build report nếu distribution hỗ trợ.
10. **Kiểm tra executable:** chạy native integration tests cho reflection, proxy, resource, serialization, JNI và URL protocol thực sự dùng.
11. **So sánh artifact:** xem metadata diff, binary size, startup, memory và các warning mới; điều tra mọi thay đổi không giải thích được.
12. **Khóa cấu hình:** pin plugin/toolchain/repository versions, lưu danh sách flags và cập nhật hướng dẫn CI để lần build sau tái lập được.

### 16.1. Kiểm tra schema và artifact

GraalVM công bố JSON Schema cho `reachability-metadata.json`. Tài liệu JDK 25 tham chiếu schema `reachability-metadata-schema-v1.2.0.json`; để validate một GraalVM release cũ hơn, dùng schema tương ứng với release đó. Đừng chỉ kiểm tra JSON parse được: schema có thể parse thành công nhưng vẫn chứa trường không hợp lệ hoặc thiếu metadata bắt buộc. [GraalVM — Reachability Metadata JSON Schema](https://www.graalvm.org/jdk25/reference-manual/native-image/metadata/)

Sau build, xác nhận metadata thực sự được đưa vào build input:

```bash
jar tf target/payment-service.jar
```

Tìm các entry trong `META-INF/native-image/`, bao gồm metadata do application, dependency và Spring AOT đóng góp. Nếu dùng Buildpacks hoặc pipeline chuyển JAR sang native image ở bước sau, xác minh JAR cuối cùng vẫn chứa metadata mà bước đó cần.

Nếu cần xem resource nào được nhúng, dùng Build Report hoặc `-H:+GenerateEmbeddedResourcesFile` trên phiên bản hỗ trợ. Việc file tồn tại trong JAR không chứng minh nó đã được include vào native executable.

## 17. Lỗi thường gặp và checklist phát hành

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `Unrecognized option` | Build script dùng flag không tồn tại ở GraalVM đang cài | Kiểm tra `native-image --version`, `--help` và plugin arguments |
| Metadata JSON parse được nhưng build báo invalid entry | Dùng sai schema, trường legacy hoặc field không được phiên bản đó hỗ trợ | Validate theo schema của target JDK |
| Missing reflection registration ở runtime | Agent chưa chạy qua code path, hoặc metadata bị lọc quá rộng | Bật exact metadata mode, chạy test đầy đủ và thêm đúng member |
| Resource không tìm thấy | Glob sai, file không có trong classpath hoặc bị loại khỏi artifact | Kiểm tra resource path và Build Report/embedded-resources file |
| Dynamic proxy lỗi | Thiếu interface hoặc thứ tự interface khác metadata | So sánh proxy definition và các interface runtime |
| Serialization lỗi | Type hoặc custom serialization path chưa đăng ký | Kiểm tra metadata serialization của đúng GraalVM release |
| JNI lookup lỗi | Thiếu class/member mà native library truy cập | Bổ sung JNI metadata và chạy integration test native |
| Flag `--enable-https` báo deprecated | Đang dùng URL handler option cũ trên JDK mới | Dùng reachability metadata cho handler nếu ứng dụng gọi `java.net.URL` |
| Buildpacks và local native build khác kết quả | Builder image dùng GraalVM/Java khác hoặc thiếu metadata trong JAR | Pin builder image và kiểm tra metadata trong artifact |
| Binary tăng kích thước bất thường | Metadata quá rộng, include toàn package hoặc resource glob quá lớn | Thu hẹp entry, thêm condition và kiểm tra report |

### Checklist trước khi phát hành

- [ ] Đã ghi rõ Spring Boot, Java, GraalVM JDK, Native Build Tools và metadata repository versions.
- [ ] Metadata format khớp với GraalVM JDK dùng trong CI.
- [ ] Không còn condition `typeReachable` trong metadata mới đã chuyển đổi.
- [ ] Reflection entries dùng `type` và giữ đủ constructor/method/field cần thiết.
- [ ] Resource regex đã được chuyển đổi có chủ đích sang glob hoặc giữ legacy format tương thích.
- [ ] Proxy metadata giữ đúng danh sách và thứ tự interface.
- [ ] Serialization metadata phù hợp schema GraalVM mục tiêu.
- [ ] JNI metadata bao phủ các lookup từ native library.
- [ ] Metadata của dependency được Native Build Tools tải hoặc được đóng gói khi pipeline downstream cần.
- [ ] Repository release version không bị nhầm với per-module metadata version.
- [ ] Không còn build flag deprecated mà chưa có lý do giữ lại.
- [ ] Exact reachability metadata và missing-registration reporting được cấu hình đúng theo JDK major.
- [ ] `native-image.properties`, Maven `buildArgs` và Gradle `buildArgs` không khai báo option xung đột.
- [ ] Spring AOT chạy với đúng profile/build-time environment.
- [ ] Native executable đã chạy integration tests cho các đường truy cập động.
- [ ] Binary size, resource inclusion và startup được so sánh với baseline.
- [ ] Toolchain và build arguments đã được khóa để CI có thể tái lập.

## 18. Ghi nhớ

Reachability metadata và build flags là một phần của hợp đồng giữa ứng dụng, thư viện, Spring AOT và GraalVM Native Image. GraalVM JDK 23 là mốc chuyển sang định dạng `reachability-metadata.json`, thay đổi condition sang `typeReached` và hợp nhất proxy metadata; JDK 24 bổ sung serialization metadata vào reflection entries; tài liệu JDK 25 đánh dấu các URL protocol flags cũ deprecated.

Khi nâng cấp, hãy chọn schema và flag theo đúng GraalVM JDK mục tiêu, kiểm tra metadata repository cho từng dependency và chạy native tests sau khi chuyển đổi. Spring Boot AOT chuẩn bị generated assets; Native Build Tools chuyển build arguments và metadata tới Native Image; Tracing Agent giúp thu thập những đường truy cập động đã được thực thi. Chỉ khi kiểm tra cả ba phần và xác nhận trên executable cuối cùng, việc nâng cấp mới có bằng chứng rằng reflection, resources, proxy, serialization và JNI vẫn hoạt động.

### Tài liệu tham khảo

- [GraalVM JDK 21 — Reachability Metadata](https://www.graalvm.org/jdk21/reference-manual/native-image/metadata/)
- [GraalVM JDK 22 — Release Notes](https://www.graalvm.org/release-notes/JDK_22/)
- [GraalVM JDK 23 — Release Notes](https://www.graalvm.org/release-notes/JDK_23/)
- [GraalVM JDK 24 — Release Notes](https://www.graalvm.org/release-notes/JDK_24/)
- [GraalVM JDK 25 — Reachability Metadata](https://www.graalvm.org/jdk25/reference-manual/native-image/metadata/)
- [GraalVM JDK 25 — Command-line Options](https://www.graalvm.org/jdk25/reference-manual/native-image/overview/Options/)
- [GraalVM — URL Protocols in Native Image](https://www.graalvm.org/latest/reference-manual/native-image/dynamic-features/URLProtocols/)
- [GraalVM — Native Image Build Configuration](https://www.graalvm.org/jdk25.5/reference-manual/native-image/overview/BuildConfiguration/)
- [Spring Boot — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/reference/packaging/aot.html)
- [Spring Boot — Maven AOT Processing](https://docs.spring.io/spring-boot/maven-plugin/aot.html)
- [Spring Boot — Developing a Native Application](https://docs.spring.io/spring-boot/how-to/native-image/developing-your-first-application.html)
- [Native Build Tools — Maven Plugin](https://graalvm.github.io/native-build-tools/latest/maven-plugin.html)
- [Native Build Tools — Gradle Plugin](https://graalvm.github.io/native-build-tools/latest/gradle-plugin)
- [Native Build Tools — Troubleshoot Missing Configuration](https://graalvm.github.io/native-build-tools/latest/end-to-end-maven-guide.html)

