# Ổn định hợp đồng endpoint theo phiên bản

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Mô tả **hợp đồng dữ liệu** của endpoint Spring Modulith Actuator `/actuator/modulith` và phân biệt nó với những API nghiệp vụ do chính ứng dụng sở hữu.
- Nhận diện các kiểu thay đổi khi nâng phiên bản Spring Modulith, Spring Boot hoặc thay đổi cấu trúc application module.
- Thiết kế chiến lược duy trì tương thích cho dashboard, bộ kiểm tra kiến trúc, công cụ inventory hoặc automation đang đọc JSON từ endpoint.
- Viết các phép kiểm tra **schema, tham chiếu và thay đổi đồ thị module** để phát hiện hồi quy trước khi triển khai.
- Chọn khi nào tiêu thụ trực tiếp endpoint của framework và khi nào nên xây **hợp đồng ổn định do ứng dụng sở hữu** với phiên bản riêng.
- Giữ đúng các yêu cầu về endpoint exposure, phân quyền và khả năng quan sát runtime trong Spring Boot.

## 1. Bối cảnh: module graph có thể trở thành đầu vào của hệ thống khác

Trong học phần **Spring Modulith Documentation & Observability**, ta sử dụng Spring Modulith để mô tả ranh giới *application module* và quan sát tương tác giữa các phần của ứng dụng Spring Boot. Module graph, Actuator, event metrics, tracing và context propagation trả lời những câu hỏi khác nhau về kiến trúc và vận hành. Trong số đó, **Module Actuator** cung cấp hình thức đọc cấu trúc module từ một ứng dụng đang chạy.

Ví dụ hệ thống bán hàng có ba module:

- `orders`: tạo đơn và điều phối trạng thái;
- `inventory`: giữ và trừ tồn kho;
- `payments`: xử lý các nghiệp vụ thanh toán.

Một công cụ nội bộ định kỳ đọc `GET /actuator/modulith` để phát hiện module mới, quan hệ phụ thuộc không mong muốn hoặc sự thay đổi trong các bản phát hành. Ban đầu, công cụ chỉ được dùng để quan sát. Về sau, nó có thể trở thành đầu vào cho báo cáo quản trị, kiểm tra CI và dashboard triển khai.

Khi đó, một thay đổi tưởng như đơn giản — đổi tên module, đổi package, nâng Spring Modulith hoặc mở rộng JSON — có thể làm hỏng ứng dụng tiêu thụ dữ liệu. Đây là lý do cần **quản trị hợp đồng endpoint theo phiên bản**.

> **Ý chính:** `/actuator/modulith` là endpoint do framework cung cấp; **không mặc định là API công khai có đường dẫn `/v1`, `/v2` hoặc cam kết tương thích do đội ứng dụng quyết định**. Nếu có người tiêu thụ dữ liệu, đội phát triển cần định nghĩa rõ mình đang dựa vào phần nào của hợp đồng, theo phiên bản nào và kiểm tra những giả định đó khi thay đổi.

## 2. Phân biệt ba lớp phiên bản

Từ “phiên bản” trong trường hợp này có ít nhất ba nghĩa:

| Lớp phiên bản | Ai kiểm soát? | Ví dụ thay đổi | Ảnh hưởng |
| --- | --- | --- | --- |
| **Phiên bản Spring Modulith** | Dự án Spring Modulith, đội ứng dụng chọn phiên bản dependency | Một release bổ sung trường JSON hoặc thay đổi cách mô hình hóa nested module | Hình dạng hoặc ngữ nghĩa dữ liệu endpoint có thể khác. |
| **Phiên bản Spring Boot/Actuator** | Dự án Spring Boot, đội ứng dụng chọn dependency/cấu hình | Thay đổi cơ chế endpoint exposure, bảo mật, đường dẫn quản trị | Consumer có thể không truy cập được endpoint dù metadata module vẫn đúng. |
| **Phiên bản hợp đồng của công cụ nội bộ** | Đội sở hữu dashboard/adapter/API | `v1` hỗ trợ `id`, `dependencies`; `v2` thêm phân cấp module | Có thể chủ động bảo đảm tương thích và quản lý migration. |

**Không được đồng nhất** version của thư viện với version của API do ứng dụng tự xây. Một dự án chạy Spring Modulith 2.x không có nghĩa `/actuator/modulith` tự trở thành `/actuator/v2/modulith`. Ngược lại, adapter nội bộ có thể giữ `v1` ổn định qua nhiều lần nâng dependency nếu chuyển đổi dữ liệu tương thích.

Cần lưu lại **phiên bản Spring Boot, Spring Modulith, Java và cấu hình module detection** trong tài liệu phát hành. Một thay đổi trong package structure của mã ứng dụng cũng có thể làm JSON khác đi dù hai dependency không đổi phiên bản.

## 3. Hợp đồng thực tế của Module Actuator

### 3.1. Kích hoạt endpoint

Spring Modulith cung cấp `spring-modulith-actuator`; nếu đã dùng `spring-modulith-starter-insight`, thành phần Actuator thường có sẵn theo starter. Cần thêm Spring Boot Actuator tương ứng nếu không dùng starter Insight.

Ví dụ Maven khi sử dụng BOM Spring Modulith tương thích với phiên bản Spring Boot của dự án:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-actuator</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

Để cho phép truy cập HTTP vào endpoint ở môi trường được bảo vệ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,modulith
~~~

Spring Boot không mặc định expose mọi endpoint quản trị qua HTTP; **chỉ health được expose theo mặc định** trong các cấu hình chuẩn của Spring Boot. Việc bật `modulith` qua HTTP cần đi kèm kiểm soát truy cập và bảo mật mạng.

Khi ứng dụng sử dụng base path và cổng mặc định, URL thường là:

~~~http
GET /actuator/modulith HTTP/1.1
Host: localhost:8080
~~~

Path có thể khác khi đội phát triển cấu hình `management.endpoints.web.base-path`, context path, management port hoặc path mapping. **Không hard-code URL trong consumer** nếu ứng dụng có nhiều môi trường triển khai; nên lưu URL quản trị trong cấu hình của công cụ tiêu thụ.

### 3.2. JSON là bản đồ các module, khóa là tên kỹ thuật

Tài liệu chính thức Spring Modulith mô tả JSON với **tên kỹ thuật của module làm khóa ở cấp gốc**. Ví dụ minh họa:

~~~json
{
  "orders": {
    "displayName": "Orders",
    "basePackage": "com.example.shop.orders",
    "dependencies": [
      {
        "target": "inventory",
        "types": ["USES_COMPONENT"]
      },
      {
        "target": "payments",
        "types": ["EVENT_LISTENER"]
      }
    ]
  },
  "inventory": {
    "displayName": "Inventory",
    "basePackage": "com.example.shop.inventory",
    "dependencies": []
  },
  "payments": {
    "displayName": "Payments",
    "basePackage": "com.example.shop.payments",
    "dependencies": []
  }
}
~~~

Đây là **dữ liệu giả lập** với các module thương mại điện tử, nhằm minh họa **cấu trúc** mà Spring Modulith công bố; các dependency và hướng phụ thuộc thực tế tùy mã nguồn.

| JSONPath | Ý nghĩa |
| --- | --- |
| `$.{moduleName}` | Khóa tên kỹ thuật module, cũng là đích mà `dependencies[].target` tham chiếu. |
| `$.{moduleName}.displayName` | Tên hiển thị phù hợp cho con người đọc. |
| `$.{moduleName}.basePackage` | Java base package dùng cho module. |
| `$.{moduleName}.dependencies[]` | Các quan hệ phụ thuộc đi ra từ module hiện tại. |
| `$.{moduleName}.dependencies[].target` | Tên kỹ thuật module được phụ thuộc. |
| `$.{moduleName}.dependencies[].types[]` | Các loại quan hệ, chẳng hạn `DEFAULT`, `USES_COMPONENT`, `EVENT_LISTENER`. |
| `$.{moduleName}.parent` | Tên module cha, nếu có; thuộc các phiên bản hỗ trợ nested module. |
| `$.{moduleName}.nested` | Tên các module lồng nhau, nếu có; thuộc các phiên bản hỗ trợ nested module. |

**Lưu ý phiên bản:** Tài liệu 1.3/1.4/2.1/2.2 có mô tả các trường `parent` và `nested` cho nested module. Đối với ứng dụng chạy release cũ hơn hoặc không có nested module, **không nên giả định hai trường này luôn có mặt**. Khi bảo trì, đối chiếu đúng tài liệu của release đang triển khai.

Một số điều **không nên giả định**:

- Root luôn có trường `modules` chứa mảng: ví dụ tài liệu dùng **object với khóa động**.
- Payload có sẵn `schemaVersion`, `apiVersion` hoặc `appVersion`: đây **không phải các trường được mô tả** trong contract mẫu của Module Actuator.
- `dependencies[]` hoặc `types[]` có thứ tự ổn định để so sánh theo chuỗi.
- Mọi module luôn có cùng tập trường tùy chọn.
- `displayName` luôn bất biến và phù hợp làm định danh dài hạn.
- JSON này là sổ nhật ký tương tác runtime: đây là **thông tin cấu trúc module**, không phải timeline thực thi hay dữ liệu kết quả nghiệp vụ.

### 3.3. Endpoint không tự bảo đảm nghiệp vụ đúng

Nếu module graph xác nhận `orders` phụ thuộc đúng vào API của `payments`, điều đó giúp hiểu **thiết kế tương tác**, không cho biết tiền đã thu chính xác hay một event đã được xử lý duy nhất. Để kiểm chứng vận hành, kết hợp Actuator với metrics, distributed traces và context propagation; để chứng minh quy tắc nghiệp vụ, cần kiểm thử, transaction, idempotency và đối soát.

Nói cách khác, **tính ổn định của endpoint** là bài toán về khả năng tiêu thụ metadata giữa các phiên bản. Nó độc lập với câu hỏi **workflow nghiệp vụ có hợp lệ không**.

## 4. Những thay đổi nào làm vỡ hợp đồng?

Giả sử dashboard đang đọc JSON từ `/actuator/modulith`. Ta nên phân biệt:

| Thay đổi | Ví dụ | Nguy cơ với consumer | Cách xử lý |
| --- | --- | --- | --- |
| **Đổi hình dạng** | Root map thành mảng, đổi tên `dependencies` | Có thể làm parser lỗi ngay. | Coi là thay đổi phá vỡ hợp đồng; cần adapter hoặc nâng consumer có kiểm soát. |
| **Đổi kiểu dữ liệu** | `types` từ array thành string | Lỗi deserialize hoặc dùng sai kiểu. | Schema test phát hiện trước phát hành. |
| **Bỏ trường bắt buộc** | Thiếu `basePackage` mà công cụ phụ thuộc | Có thể mất thông tin hoặc lỗi xử lý. | Kiểm tra contract tối thiểu và quy tắc fallback rõ ràng. |
| **Thêm trường tùy chọn** | Có `parent` cho nested module | Consumer strict có thể từ chối dù dữ liệu cũ vẫn dùng được. | Ưu tiên parser chấp nhận trường chưa biết; bổ sung khả năng mới sau. |
| **Đổi định danh module** | `orders` thành `sales-orders` | Dashboard mất lịch sử, phép so sánh đồ thị nhận như xóa/thêm node. | Lập mapping/migration nếu ID được lưu bền. |
| **Đổi tên hiển thị** | `Orders` thành `Order Management` | UI thay đổi; không nên phá quan hệ tham chiếu. | Dùng khóa kỹ thuật cho định danh, displayName chỉ để hiển thị. |
| **Đổi đường dẫn/exposure** | `/actuator` đổi base path, endpoint không expose | Trả 404/401/403 dù payload chưa thay đổi. | Cấu hình URL và quyền, kiểm tra connectivity riêng. |
| **Thêm loại dependency** | Framework bổ sung một giá trị `types[]` | Parser enum đóng có thể lỗi. | Xử lý giá trị chưa biết theo chính sách; ghi nhận để xem xét. |
| **Tái cấu trúc đồ thị** | `inventory` chuyển thành nested module; thay basePackage | Có thể là thay đổi **có chủ đích về kiến trúc**, không phải regression của framework. | Review bằng architectural diff; quyết định có chấp nhận hay không. |
| **Thay định nghĩa mô hình module** | Bổ sung module detection customization | Payload đổi dù framework version giữ nguyên. | Kiểm tra cấu hình module detection cùng bản mã nguồn. |

Hai trục **tương thích dữ liệu** và **tương thích kiến trúc** cần được đánh giá riêng. Đổi tên module có thể đúng theo yêu cầu refactor nhưng vẫn phá dashboard; ngược lại, JSON có hình dạng hoàn toàn hợp lệ vẫn có thể chứa dependency vi phạm ranh giới mong muốn.

## 5. Chính sách tương thích theo người tiêu thụ

Không phải consumer nào cũng cần mức cam kết giống nhau.

| Consumer | Mục tiêu | Chính sách đề xuất |
| --- | --- | --- |
| **Người vận hành xem trực tiếp qua curl** | Điều tra trạng thái hiện tại | Có thể đọc trực tiếp endpoint của release đang chạy, tra tài liệu của release đó. |
| **Dashboard nội bộ cùng chu kỳ triển khai** | Hiển thị module và quan hệ | Đọc trực tiếp có contract test và triển khai đồng bộ. |
| **Công cụ CI kiểm tra architecture drift** | So sánh bản mã nguồn với baseline | Normalize graph, kiểm tra schema và review sự thay đổi có chủ đích. |
| **Hệ thống nhiều đội, nhiều chu kỳ phát hành** | Thu metadata từ nhiều ứng dụng/dòng version | Xây adapter sang schema ổn định thuộc quyền sở hữu của nền tảng. |
| **Khách hàng hoặc đối tác bên ngoài** | Tích hợp có cam kết lâu dài | Cân nhắc API chuyên biệt có version, auth, chính sách tương thích và tài liệu công khai; không mặc nhiên expose Actuator trực tiếp. |

### 5.1. Khi nào tiêu thụ trực tiếp là hợp lý?

Tiêu thụ trực tiếp `/actuator/modulith` có thể đủ khi:

- công cụ và ứng dụng được nâng phiên bản cùng đợt;
- số consumer nhỏ, biết rõ ai sở hữu;
- không lưu lại khóa module như định danh bất biến qua nhiều năm;
- có kiểm thử trên artifact triển khai thật và có cách rollback;
- chỉ truy cập trong phạm vi quản trị đã bảo vệ.

Ngay cả trường hợp này, consumer vẫn nên **chấp nhận trường bổ sung và trường tùy chọn**, kiểm tra những trường bắt buộc thực sự dùng, xử lý lỗi HTTP và ghi nhận version của ứng dụng nguồn.

### 5.2. Khi nào cần một adapter riêng?

Nên tạo một lớp adapter/facade khi:

- dashboard tập trung đọc dữ liệu từ nhiều ứng dụng đang dùng các release Spring Modulith khác nhau;
- dữ liệu được lưu dài hạn để theo dõi thay đổi kiến trúc;
- cần bảo đảm một hợp đồng công khai cho nhiều nhóm độc lập;
- phải đổi cách biểu diễn để phù hợp với hệ thống khác, ví dụ từ object khóa động sang mảng node;
- cần ẩn `basePackage`, chi tiết phụ thuộc nội bộ hoặc metadata nhạy cảm đối với nhóm người dùng không được quyền xem.

Một adapter có thể được triển khai trong cổng quản trị nội bộ hay dịch vụ thu thập metadata, không nhất thiết phải gắn trực tiếp lên ứng dụng nghiệp vụ. Adapter đọc endpoint Modulith, **chuyển đổi có kiểm soát**, rồi xuất một API do chính đội nền tảng định nghĩa.

## 6. Ví dụ thiết kế hợp đồng ổn định do ứng dụng sở hữu

Giả sử ta muốn cung cấp endpoint nội bộ:

~~~http
GET /internal/architecture/v1/modules HTTP/1.1
Host: architecture.example.internal
~~~

Payload **tự thiết kế**, không phải payload chuẩn của Spring Modulith:

~~~json
{
  "schemaVersion": "1",
  "source": {
    "service": "shop-service",
    "springModulithVersion": "2.x",
    "applicationRevision": "abc123"
  },
  "modules": [
    {
      "id": "inventory",
      "name": "Inventory",
      "basePackage": "com.example.shop.inventory",
      "parentId": null,
      "dependencies": []
    },
    {
      "id": "orders",
      "name": "Orders",
      "basePackage": "com.example.shop.orders",
      "parentId": null,
      "dependencies": [
        {"targetId": "inventory", "kinds": ["USES_COMPONENT"]}
      ]
    }
  ]
}
~~~

**Quy ước cần công bố rõ trong tài liệu của adapter:**

1. `schemaVersion` là **phiên bản hợp đồng của adapter**, do đội ứng dụng/nền tảng quản lý; Spring Modulith không tự thêm trường này vào endpoint gốc.
2. `source.springModulithVersion` và `source.applicationRevision` là metadata do đội vận hành cung cấp từ build/deployment; giá trị mẫu không có nghĩa runtime có thể tự suy ra chúng từ JSON Modulith.
3. `modules` là mảng **được sắp xếp theo `id`**, tránh lệ thuộc thứ tự property của JSON object gốc.
4. `dependencies` được sắp xếp theo `targetId`; `kinds` theo tên, để snapshot và diff ổn định.
5. `parentId: null` biểu thị không xác định module cha trong **schema adapter v1**; adapter cần chính sách riêng để diễn giải trường nguồn vắng mặt trong các phiên bản cũ.
6. Các khóa `id` là **tên kỹ thuật module nguồn**, trừ khi đội thiết kế một cơ chế ánh xạ ID riêng. Nếu tên nguồn đổi, cần migration đối với hệ thống lưu lịch sử.
7. API v1 có chính sách rõ khi gặp một `types[]` chưa từng biết: có thể chuyển tên nguyên văn, đánh dấu chưa nhận diện hoặc từ chối có thông báo, tùy hợp đồng.

### 6.1. Sơ đồ ranh giới trách nhiệm

~~~mermaid
flowchart LR
    A["Ứng dụng Spring Boot"] --> B["Spring Modulith\nGET /actuator/modulith"]
    B --> C["Adapter kiểm tra schema\nvà chuẩn hóa graph"]
    C --> D["API nội bộ\n/v1/modules"]
    D --> E["Dashboard kiến trúc"]
    D --> F["Công cụ CI / báo cáo"]
    G["BOM + release notes"] --> A
    H["Contract tests"] --> C
    I["Baseline / diff"] --> F
~~~

Lợi ích của adapter là khả năng giữ nguyên `/v1/modules` dù endpoint framework có thay đổi tương thích được. Đổi lại, đội sở hữu adapter phải gánh trách nhiệm versioning, kiểm thử và xử lý dữ liệu sai; adapter không biến mọi breaking change của framework thành tương thích một cách tự động.

### 6.2. Nguyên tắc “tolerant reader”

Consumer nên:

- đọc các trường cần thiết thay vì giả định toàn bộ JSON có tập property cố định;
- bỏ qua trường mới chưa dùng nhưng **không âm thầm bỏ qua trường bắt buộc mất đi**;
- phân biệt `null`, trường vắng mặt và mảng rỗng theo hợp đồng;
- không cố định thứ tự module/dependency từ JSON gốc;
- kiểm tra kiểu dữ liệu, target tham chiếu, tên kỹ thuật trùng hoặc không hợp lệ;
- theo dõi release nguồn để phục vụ điều tra khi sai khác.

**Tolerant reader không có nghĩa là “nuốt” mọi lỗi.** Ví dụ nếu `dependencies[].target` không tìm thấy trong danh sách module, công cụ phải ghi nhận dữ liệu mâu thuẫn thay vì tạo ra một đồ thị sai nhưng vẫn báo pass.

## 7. Kiểm chứng hợp đồng bằng dữ liệu thực tế

Một kiểm tra đáng tin cậy nên đi qua ba tầng:

1. **Transport/access:** endpoint tồn tại, trả kết quả hợp lệ, caller có quyền.
2. **Schema/reference:** JSON có hình dạng, kiểu và tham chiếu đúng kỳ vọng của consumer.
3. **Architectural drift:** cấu trúc module đã thay đổi như thế nào so với baseline được duyệt.

Ba tầng này cần thông báo lỗi khác nhau. Không nên báo “module bị xóa” khi request thực tế trả 401 hoặc 404 do lỗi cấu hình Actuator.

### 7.1. Tầng transport: thu payload có kiểm tra lỗi

Ví dụ chạy ở máy có quyền truy cập endpoint quản trị trong môi trường CI/staging:

~~~bash
curl --fail-with-body --silent --show-error \
  --header "Accept: application/json" \
  --output modulith.json \
  "http://localhost:8080/actuator/modulith"
~~~

Nếu endpoint được bảo vệ, CI phải cung cấp cơ chế xác thực phù hợp (token, mTLS hoặc gateway) theo chính sách của tổ chức; không nhúng credential thật vào script và repository. Cần kiểm tra HTTP status cùng thông tin lỗi. Cổng, base path và scheme có thể khác theo môi trường.

Lưu ý lệnh minh họa trên dùng tùy chọn `--fail-with-body` của các phiên bản curl hỗ trợ tùy chọn đó. Với môi trường cũ, dùng cách kiểm tra HTTP status tương đương.

### 7.2. Tầng schema: kiểm tra điều consumer cần

Đây là ví dụ với `jq` (công cụ bên ngoài Spring Modulith) để kiểm tra cấu trúc tối thiểu. Ví dụ giả định các module đều có `displayName`, `basePackage`, `dependencies` theo JSON chính thức, và `parent`, `nested` là tùy chọn.

~~~bash
jq -e '
  type == "object" and
  (to_entries | all(.[];
    (.key | type == "string") and
    (.value | type == "object") and
    (.value.displayName | type == "string") and
    (.value.basePackage | type == "string") and
    (.value.dependencies | type == "array") and
    ((.value.parent == null) or (.value.parent | type == "string")) and
    ((.value.nested == null) or (.value.nested | type == "array")) and
    (.value.dependencies | all(.[];
      (.target | type == "string") and
      (.types | type == "array") and
      (.types | all(.[]; type == "string"))
    ))
  ))
' modulith.json
~~~

Đoạn kiểm tra là **contract tối thiểu của ví dụ**. Nó không cố đóng băng toàn bộ cấu trúc JSON và không giả định chỉ có đúng ba giá trị `types[]`, để consumer có thể nhận biết các giá trị mới mà không crash ngay.

Cần thêm bước **kiểm tra tham chiếu**: mỗi `dependencies[].target` phải trỏ tới một khóa module có thật; mỗi `parent` có giá trị cũng phải là khóa hợp lệ; các tên trong `nested` cần đối chiếu quan hệ cha–con nếu chính sách của hệ thống yêu cầu.

Ví dụ kiểm tra target cho từng dependency:

~~~bash
jq -e '
  . as $graph
  | all(to_entries[];
      all(.value.dependencies[];
        .target as $target
        | $graph | has($target)
      )
    )
' modulith.json
~~~

Các phép kiểm tra giúp phát hiện payload **không hợp đồng**. Chúng chưa chứng minh dependency được phép theo quy tắc kiến trúc; điều đó cần một bộ luật riêng, ví dụ kiểm tra trực tiếp bằng Spring Modulith trong test.

### 7.3. Tầng drift: chuẩn hóa trước khi so sánh

Không nên lưu snapshot bằng cách so sánh nguyên văn toàn bộ JSON, vì thứ tự property, thứ tự module hoặc phần tử mảng có thể khiến diff ồn. Với `jq`, có thể chuẩn hóa dữ liệu như sau:

~~~bash
jq '
  to_entries
  | map({
      id: .key,
      displayName: .value.displayName,
      basePackage: .value.basePackage,
      parent: (.value.parent // null),
      nested: ((.value.nested // []) | sort),
      dependencies: (
        .value.dependencies
        | map({
            target: .target,
            types: (.types | sort)
          })
        | sort_by(.target)
      )
    })
  | sort_by(.id)
' modulith.json > module-graph.normalized.json
~~~

Sau đó so sánh `module-graph.normalized.json` với baseline đã duyệt trong repository hoặc artifact store. Khi có thay đổi:

- Nếu chỉ thêm module hợp lệ theo yêu cầu, review và cập nhật baseline.
- Nếu phát sinh dependency mới không mong muốn, chặn merge hoặc yêu cầu người sở hữu kiến trúc giải thích.
- Nếu mất trường bắt buộc vì nâng phiên bản, báo **contract break** và sửa adapter trước.
- Nếu đổi base package theo refactor, xác minh đổi tên là chủ đích và cập nhật mapping/lịch sử nếu cần.

**Không tự động ghi đè baseline sau mọi build**, vì như vậy phép kiểm tra chỉ xác nhận rằng “hiện trạng giống chính nó”. Baseline cần một bước xét duyệt và sự giải thích cho thay đổi kiến trúc.

### 7.4. Tránh snapshot test quá cứng

Chia mức kiểm thử:

| Mức kiểm thử | Thứ cần giữ ổn định | Không nên kiểm tra |
| --- | --- | --- |
| **Smoke** | Endpoint truy cập được trong môi trường được cấp quyền. | Không yêu cầu toàn bộ module cố định nếu mới chỉ smoke. |
| **Schema** | Những property, kiểu và tham chiếu consumer thực sự cần. | Không giả định “cấm mọi property lạ”. |
| **Semantic** | Quan hệ target trỏ đúng; các quy tắc module của tổ chức. | Không suy ra business workflow đúng chỉ từ graph. |
| **Baseline/diff** | Thay đổi kiến trúc phải được review. | Không so sánh chuỗi JSON thô theo thứ tự. |
| **Adapter contract** | `/v1/modules` vẫn giữ schema và ý nghĩa cam kết. | Không đặt kỳ vọng framework sẽ giữ v1 thay cho đội adapter. |

## 8. Quy trình nâng phiên bản Spring Boot và Spring Modulith

Một quy trình kiểm soát thay đổi có thể triển khai như sau:

~~~mermaid
flowchart TD
    A["Chốt phiên bản hiện tại\nvà snapshot graph"] --> B["Xem release notes\nvà tài liệu đúng version"]
    B --> C["Nâng BOM / dependency\ntrong nhánh thay đổi"]
    C --> D["Chạy test cấu trúc module"]
    D --> E["Khởi động ứng dụng\nở staging"]
    E --> F["Kiểm tra HTTP/exposure/security"]
    F --> G["Kiểm tra schema và target"]
    G --> H["So sánh graph đã chuẩn hóa"]
    H --> I{"Có breaking change?"}
    I -->|"Có"| J["Sửa adapter/consumer\nvà lên kế hoạch migration"]
    I -->|"Không"| K["Review khác biệt kiến trúc"]
    J --> K
    K --> L["Triển khai có giám sát\nvà rollback khả dụng"]
~~~

### Bước 1: chốt phiên bản và baseline

- Ghi nhận Spring Boot, Spring Modulith và bộ dependency thực tế; dùng BOM/khóa phiên bản để tránh trôi phiên bản khó phát hiện.
- Lưu snapshot normalized từ artifact đang chạy **hoặc** bộ test tạo mô hình module cùng revision.
- Ghi nhận URL, cách xác thực, role, management port, base path và deployment profile.

### Bước 2: đọc tài liệu đúng phiên bản

Tài liệu chính thức cho phép đọc trang theo nhánh release (ví dụ `/reference/1.4/`, `/reference/2.1/`, `/reference/2.2/`). Khi nâng cấp, hãy đối chiếu release notes/migration guide của **phiên bản nguồn và đích** để phát hiện sự khác biệt trong core module discovery, nested module và Actuator.

Điểm hữu ích trong lịch sử: tài liệu Spring Modulith cho biết nested application modules được hỗ trợ từ **1.3**; trong contract Modulith Actuator ở các tài liệu mới, `parent` và `nested` là các trường liên quan. Đây là ví dụ thực tế về việc **năng lực mô hình module mở rộng theo release**. Không nên tuyên bố schema thay đổi bắt buộc trong mọi ứng dụng: khi không sử dụng nested module, payload có thể không xuất hiện thông tin này.

### Bước 3: kiểm thử với artifact thật

- Chạy kiểm thử ranh giới module từ cùng bản mã nguồn sẽ triển khai (ví dụ `ApplicationModules.of(ShopApplication.class).verify()` trong bài test đã cấu hình phù hợp).
- Khởi động bản build ở môi trường staging đủ gần production.
- Gửi request qua đúng đường quản trị và quyền truy cập mà collector sẽ sử dụng.
- Kiểm tra schema và graph từ payload **thực**; không chỉ đọc JSON mẫu trong tài liệu.
- Thử cả quy trình khi endpoint trả `401`, `403`, `404`, timeout và JSON thiếu trường, để dashboard/CI báo lỗi rõ ràng.

### Bước 4: đánh giá rolling deployment và dữ liệu nhiều phiên bản

Trong triển khai rolling hoặc blue-green, cùng một thời điểm có thể có hai phiên bản ứng dụng trả **hai đồ thị module khác nhau**. Nếu collector đọc qua load balancer, hai lần gọi liên tiếp có thể nhận hai snapshot khác nhau.

Nên:

1. Gắn thông tin release/build vào **record do collector lưu** hoặc API adapter.
2. Thu dữ liệu theo instance/deployment revision khi cần so sánh chính xác.
3. Tránh dùng một baseline để so sánh đồng thời dữ liệu của bản cũ và bản mới mà không phân biệt revision.
4. Chỉ cập nhật baseline kiến trúc được duyệt sau khi xác nhận kết quả của phiên bản đích.

Đây là vấn đề **topology và chu kỳ triển khai**, không chỉ là parser JSON.

### Bước 5: triển khai và rollback

Khi adapter/công cụ tiêu thụ cần thay đổi, có thể triển khai consumer hỗ trợ cả hai dạng dữ liệu trước, sau đó nâng producer. Nếu breaking change lớn, duy trì hai phiên bản của API **do ứng dụng sở hữu** trong giai đoạn chuyển tiếp. Có phương án quay lại dependency/build trước đó khi phát hiện một schema không thể xử lý.

Không nên tự động biến endpoint framework thành `/v2` bằng cách đổi path trong cấu hình Actuator rồi coi là đã version hóa: việc đổi path **không cung cấp parser, mapping và chính sách tương thích dữ liệu**.

## 9. Những sai lầm thường gặp

### 9.1. Đóng đinh toàn bộ JSON như một string

**Sai:** test `assertEquals(expectedString, responseBody)`.

Vì JSON object không có ý nghĩa thứ tự property, so sánh string có thể báo lỗi giả. Hãy parse JSON, kiểm tra trường cần thiết và dùng normalization trước khi diff.

### 9.2. Dùng tên hiển thị làm khóa trong database kiến trúc

**Sai:** lưu `displayName` làm khóa định danh module để nối dữ liệu qua nhiều release.

Tên hiển thị có thể đổi vì thuật ngữ nghiệp vụ hoặc bản địa hóa. Nếu muốn dùng danh tính nguồn, khóa kỹ thuật `moduleName` phù hợp hơn; nếu cần duy trì ID qua refactor, định nghĩa ID ổn định riêng trong adapter và quản lý migration.

### 9.3. Coi thêm module mới là lỗi schema

Một module mới thêm vào root object không phải tự thân là phá vỡ JSON contract. Nó có thể là thay đổi kiến trúc đáng review. Hãy đánh giá bằng **architectural diff**, không mặc định chặn ở tầng parser.

### 9.4. Đánh đồng HTTP status với schema

`404 Not Found` có thể do endpoint chưa expose, dependency không có, base path thay đổi hoặc route không đến đúng management server. `401/403` liên quan đến authentication/authorization. Không nên tự suy ra rằng framework “đã bỏ trường module” khi chưa có một phản hồi JSON hợp lệ.

### 9.5. Expose `modulith` công khai vì dashboard cần đọc

Metadata có thể tiết lộ package, tên module và cấu trúc phụ thuộc nội bộ. Chỉ bật endpoint cho các actor được ủy quyền, ưu tiên management network hoặc gateway phù hợp, dùng TLS và nguyên tắc đặc quyền tối thiểu. Công cụ công khai có thể sử dụng adapter đã lọc dữ liệu.

### 9.6. Kỳ vọng Actuator là API versioned chính thức cho bên thứ ba

Module Actuator là giao diện **quản trị/quan sát ứng dụng**. Tài liệu mô tả cấu trúc response, nhưng đội phát triển không nên suy ra có cam kết semantic versioning của một public business API do tổ chức sở hữu. Khi yêu cầu hợp đồng độc lập, đội phải tự thiết kế và kiểm thử.

### 9.7. Nhầm cấu trúc module với runtime tracing

Payload `/actuator/modulith` là mô hình cấu trúc; nó không chứa toàn bộ span, số lần event được phát hoặc kết quả giao dịch. Khi vấn đề là mất trace/context, hãy kiểm tra Micrometer/observability/exporter và propagation ở những ranh giới async; không đặt thêm trường tự nghĩ vào Modulith endpoint rồi chờ framework gửi dữ liệu đó.

## 10. Một chính sách hợp đồng mẫu cho nhóm phát triển

Có thể đặt ra chính sách ngắn cho công cụ `architecture-catalog`:

> **Nguồn:** `GET /actuator/modulith` chỉ được thu trong mạng quản trị, từ các ứng dụng đã đăng ký.  
> **Nguồn sự thật về phiên bản:** dependency tree + build revision của từng ứng dụng.  
> **Định dạng ổn định cho consumer:** `GET /internal/architecture/v1/modules` do adapter sở hữu.  
> **V1 bảo đảm:** có `schemaVersion`, danh sách module với `id`, `name`, `dependencies`, thứ tự ổn định; trường mới có thể được bổ sung mà không xóa các trường cũ.  
> **Phá vỡ hợp đồng:** bỏ trường bắt buộc, đổi ý nghĩa hoặc đổi kiểu dữ liệu làm consumer v1 hiện hữu không còn hiểu đúng phải qua version mới hoặc kế hoạch migration.  
> **Quy trình release:** contract test và graph diff trước khi duyệt; lưu artifact so sánh với revision; rollback khả dụng.  
> **Quy trình bảo mật:** role nội bộ và kiểm toán truy cập; không sao chép metadata nhạy cảm ra hệ thống công cộng.

Đây là **ví dụ chính sách của một tổ chức**. Nó **không phải** một cấu hình tự động, cũng không phải cam kết sẵn có của Spring Modulith.

## 11. Câu hỏi ôn tập và bài tập

1. Dashboard mong root JSON có mảng `modules`, nhưng `/actuator/modulith` trả object với tên module làm khóa. Sai lệch thuộc tầng **schema** hay tầng **architectural drift**? Bạn sẽ sửa ở đâu?
2. Sau khi nâng Spring Modulith, một số module có thêm `parent`. Consumer cũ từ chối JSON do gặp property chưa biết. Đây là lỗi tương thích theo hướng nào? Một tolerant reader nên hành xử ra sao?
3. Nhóm đổi `com.example.shop.inventory` thành `com.example.shop.stock`, đồng thời đổi module `inventory` thành `stock`. Những thành phần nào chịu tác động nếu hệ thống dùng `moduleName` làm khóa lịch sử?
4. Trong rolling deployment, collector nhận lần lượt hai module graphs khác nhau nhưng cả hai đều hợp lệ. Cần bổ sung metadata nào trước khi kết luận đây là hồi quy?
5. Viết một kiểm tra xác nhận mọi `dependencies[].target` đều tham chiếu module có trong root JSON.
6. Vì sao test `ApplicationModules.verify()` và schema test của endpoint đều cần thiết nhưng không thay thế cho nhau?
7. Với yêu cầu cung cấp module graph cho đối tác bên ngoài trong nhiều năm, nên tiêu thụ trực tiếp Actuator hay xây API versioned riêng? Hãy nêu tiêu chí quyết định, cơ chế bảo mật và cách chuyển đổi dữ liệu.

## 12. Tổng kết

Để ổn định hợp đồng endpoint Spring Modulith qua các phiên bản, cần nắm bốn nguyên tắc:

1. **Biết rõ hợp đồng nguồn:** `/actuator/modulith` trả metadata cấu trúc ứng dụng theo schema của Spring Modulith; endpoint không tự áp dụng versioning của API nghiệp vụ do bạn sở hữu.
2. **Phân biệt thay đổi:** schema/transport, dependency version, cấu trúc application module và lịch triển khai đều có thể khiến consumer quan sát được kết quả khác nhau.
3. **Kiểm chứng thay vì phỏng đoán:** xác thực HTTP, kiểm tra schema và tham chiếu, chuẩn hóa graph để so sánh, review baseline, kiểm tra quyền và nguồn release.
4. **Chủ động sở hữu hợp đồng dài hạn:** khi có nhiều consumer độc lập, tạo adapter/API có version và chính sách tương thích; giữ Actuator trong phạm vi quản trị phù hợp.

Sử dụng các nguyên tắc trên giúp hệ thống Spring Boot tiếp tục cung cấp **module graph và metadata kiến trúc đáng tin cậy** khi nâng Spring Modulith, đồng thời hỗ trợ việc liên hệ dữ liệu cấu trúc với metrics, tracing và context propagation để quan sát hành vi vận hành. Metadata có cấu trúc ổn định giúp phát hiện thay đổi kiến trúc tốt hơn; tính đúng đắn nghiệp vụ vẫn cần bằng chứng riêng.

### Tài liệu tham khảo

- [Spring Modulith — Production-ready Features: Application Module Actuator, schema JSON và Insight](https://docs.spring.io/spring-modulith/reference/production-ready.html).
- [Spring Modulith — Fundamentals: Application Modules và Nested Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html).
- [Spring Modulith — Reference 1.3: Production-ready Features](https://docs.spring.io/spring-modulith/reference/1.3/production-ready.html).
- [Spring Modulith — Reference 2.1: Production-ready Features](https://docs.spring.io/spring-modulith/reference/2.1/production-ready.html).
- [Spring Modulith — Reference 2.2: Production-ready Features](https://docs.spring.io/spring-modulith/reference/2.2/production-ready.html).
- [Spring Boot — Actuator Endpoints, HTTP Exposure và Security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).
