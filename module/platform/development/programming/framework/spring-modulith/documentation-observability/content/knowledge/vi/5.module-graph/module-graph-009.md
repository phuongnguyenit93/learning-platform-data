# Vẽ sơ đồ module từ JSON endpoint

## 1. Bài toán: từ metadata của runtime đến hình ảnh kiến trúc

Trong một ứng dụng Spring Boot tổ chức theo **Spring Modulith**, mỗi *application module* đại diện cho một vùng chức năng có API và ranh giới riêng. Khi một ứng dụng có hàng chục module, việc đọc từng package hay kiểm tra JSON thủ công không đủ trực quan để trả lời: module nào phụ thuộc module nào, điểm kết nối tập trung ở đâu, và quan hệ nào phát sinh qua listener sự kiện?

Spring Modulith cung cấp endpoint `/actuator/modulith` để xuất **cấu trúc module và phụ thuộc ở thời điểm ứng dụng đang chạy** dưới dạng JSON. Từ dữ liệu đó, ta có thể dựng **module graph** bằng Mermaid hoặc Graphviz, đưa vào tài liệu kỹ thuật và so sánh các bản triển khai.

Bài này thuộc nhóm **Module graph** của **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**: dùng Spring Modulith để tài liệu hóa ranh giới application module, hỗ trợ kiểm chứng kiến trúc khi vận hành và kết nối với những tín hiệu như event metrics, traces hoặc context propagation. Sơ đồ JSON trình bày **quan hệ kiến trúc được nhận diện**, không phải nhật ký những lời gọi thực tế. Điều này cần được giữ rõ trong toàn bộ quy trình chuyển đổi.

Sau bài học, bạn có thể lấy JSON từ endpoint, xác định đúng chiều cạnh, vẽ một đồ thị bằng tay, viết script sinh Mermaid tự động, xử lý module độc lập và module lồng nhau, rồi xác minh graph không bỏ sót thông tin.

## 2. Dữ liệu JSON của `/actuator/modulith` có những gì?

Theo schema do Spring Modulith công bố, JSON của endpoint `modulith` là một **object**, trong đó mỗi khóa cấp cao là **tên kỹ thuật của application module**. Giá trị ứng với khóa đó chứa metadata và các phụ thuộc đi ra.

| Trường trong JSON | Ý nghĩa khi chuyển sang graph |
| --- | --- |
| Khóa `{moduleName}` | Định danh kỹ thuật của module; được tham chiếu bởi `dependencies.target`. |
| `displayName` | Tên hiển thị của module, phù hợp làm nhãn nút. |
| `basePackage` | Package gốc giúp liên kết nút với mã nguồn. |
| `dependencies[]` | Danh sách phụ thuộc **đi ra** từ module đang xét. |
| `dependencies[].target` | Khóa của module mà module hiện tại phụ thuộc. |
| `dependencies[].types[]` | Các loại phụ thuộc, có thể chứa nhiều giá trị. |
| `parent` (tùy chọn) | Module cha nếu có module lồng nhau. |
| `nested` (tùy chọn) | Thông tin các module con, dùng để nhóm hình nếu cần. |

Trong `types[]`, ba giá trị được tài liệu hóa là:

- `DEFAULT`: phụ thuộc loại tham chiếu kiểu thông thường.
- `USES_COMPONENT`: phụ thuộc liên quan đến một Spring component/bean.
- `EVENT_LISTENER`: quan hệ phụ thuộc được nhận diện thông qua listener sự kiện.

**Quy tắc quan trọng nhất:** nếu phần JSON của module `ordering` chứa `{"target":"inventory"}`, cạnh phải đi theo chiều **`ordering → inventory`**. Đó là chiều *module hiện tại phụ thuộc module đích*. Không tự đảo mũi tên theo trực giác về luồng nghiệp vụ.

Ví dụ, `notification` có listener tham chiếu kiểu `OrderPlaced` khai báo ở `ordering`, nên dependency graph có thể vẽ `notification → ordering` mang nhãn `EVENT_LISTENER`. Trong khi đó, luồng phát event nghiệp vụ có thể đi theo chiều `ordering → notification`. Hai sơ đồ có ngữ nghĩa khác nhau.

## 3. Bật endpoint và lưu snapshot JSON

### 3.1. Khai báo dependency

Với dự án Gradle Kotlin DSL đã quản lý phiên bản Spring Boot và Spring Modulith tương thích:

~~~kotlin
dependencies {
    runtimeOnly("org.springframework.modulith:spring-modulith-actuator")
    runtimeOnly("org.springframework.boot:spring-boot-starter-actuator")
}
~~~

Nếu ứng dụng đã dùng `spring-modulith-starter-insight`, hỗ trợ Spring Modulith Actuator đã nằm trong starter tổng hợp nên không cần khai báo lại chỉ để lấy module graph. Trong dự án Maven, có thể dùng hai artifact tương ứng với scope runtime. Cần đồng bộ version theo BOM của dự án.

Ví dụ `application.yml` cho môi trường phát triển:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,modulith"
~~~

`health` là Actuator endpoint của Spring Boot; `modulith` là endpoint của Spring Modulith. Việc expose qua HTTP không thay cho cấu hình access và Spring Security; trong production, nên giới hạn truy cập vì dữ liệu chứa thông tin cấu trúc nội bộ của ứng dụng.

### 3.2. Lấy dữ liệu

Giả sử ứng dụng đang nghe trên `localhost:8080` và management base path là mặc định:

~~~bash
curl --fail --silent --show-error --header "Accept: application/json" \
  --output modulith.json http://localhost:8080/actuator/modulith
~~~

Hoặc dùng PowerShell:

~~~powershell
Invoke-WebRequest -Uri "http://localhost:8080/actuator/modulith" -OutFile "modulith.json"
~~~

Với hệ thống có cổng management riêng hoặc `management.endpoints.web.base-path` tùy chỉnh, cần dùng URL tương ứng. Nếu có xác thực, cung cấp thông tin truy cập qua phương thức an toàn; không ghi token trong tài liệu hoặc tệp được commit.

Kiểm tra HTTP status trước khi xử lý. Một trang HTML đăng nhập, phản hồi `401/403` hoặc JSON lỗi **không phải payload module graph**.

## 4. Ví dụ JSON nhất quán để thực hành

Xét ứng dụng bán hàng gồm năm module `inventory`, `notification`, `ordering`, `payment` và `reporting`. Đây là **ví dụ minh họa**, không phải dữ liệu lấy từ một ứng dụng thật:

~~~json
{
  "inventory": {
    "displayName": "Inventory",
    "basePackage": "com.example.shop.inventory",
    "dependencies": []
  },
  "notification": {
    "displayName": "Notification",
    "basePackage": "com.example.shop.notification",
    "dependencies": [
      {
        "target": "ordering",
        "types": ["EVENT_LISTENER"]
      }
    ]
  },
  "ordering": {
    "displayName": "Ordering",
    "basePackage": "com.example.shop.ordering",
    "dependencies": [
      {
        "target": "inventory",
        "types": ["USES_COMPONENT"]
      },
      {
        "target": "payment",
        "types": ["DEFAULT", "USES_COMPONENT"]
      }
    ]
  },
  "payment": {
    "displayName": "Payment",
    "basePackage": "com.example.shop.payment",
    "dependencies": []
  },
  "reporting": {
    "displayName": "Reporting",
    "basePackage": "com.example.shop.reporting",
    "dependencies": []
  }
}
~~~

Từ dữ liệu này, ta xác định:

1. Có **5 module** vì JSON có 5 khóa cấp cao.
2. Có **3 cặp dependency có hướng**: `notification → ordering`, `ordering → inventory` và `ordering → payment`.
3. `ordering → payment` có **2 loại phụ thuộc**; giữ cả hai nhãn, tránh chỉ lấy `types[0]`.
4. `inventory` và `payment` không có dependency đi ra nhưng vẫn có cạnh đi vào.
5. `reporting` vừa không có dependency đi ra, vừa không có cạnh đi vào; nó **vẫn phải xuất hiện trên graph**.

## 5. Vẽ bằng tay bằng Mermaid

Ánh xạ đầu vào sang Mermaid theo bảng:

| JSON | Mermaid | Cách hiểu |
| --- | --- | --- |
| Mỗi khóa module | Một nút | Tạo đủ nút trước, kể cả `dependencies: []`. |
| `displayName` | Nhãn nút | Hiển thị tên dễ đọc. |
| `dependencies[].target` | Cạnh `source --> target` | `source` là module chứa phần tử dependency hiện tại. |
| `dependencies[].types[]` | Nhãn trên cạnh | Có thể chứa nhiều loại, nối chúng bằng dấu phẩy. |
| `parent`/`nested` | Nhóm `subgraph` tùy chọn | Quan hệ phân cấp, không tự tạo cạnh phụ thuộc. |

Sơ đồ tương ứng:

~~~mermaid
flowchart LR
    inventory["Inventory"]
    notification["Notification"]
    ordering["Ordering"]
    payment["Payment"]
    reporting["Reporting"]

    notification -->|"EVENT_LISTENER"| ordering
    ordering -->|"USES_COMPONENT"| inventory
    ordering -->|"DEFAULT, USES_COMPONENT"| payment
~~~

Đọc mũi tên từ **nguồn sang đích**: `ordering` cần API/kiểu từ `inventory` và `payment`; `notification` có quan hệ listener với `ordering`. `reporting` đứng riêng. Đồ thị này không khẳng định một request cụ thể đã gọi cả `inventory` lẫn `payment`.

Trong sơ đồ nhỏ, ta có thể dùng tên kỹ thuật làm Mermaid ID vì chúng an toàn. Với dữ liệu không kiểm soát được, nên dùng ID được sinh ra như `m0`, `m1` để tránh lỗi do dấu cách hoặc ký tự đặc biệt. `displayName` nên là **nhãn**, không phải khóa để nối cạnh, vì tên hiển thị có thể trùng nhau.

## 6. Tạo Mermaid tự động từ JSON bằng Node.js

Đối với hệ thống có nhiều module, hãy dùng một script cố định để có thể chạy lại sau mỗi bản phát hành. Mã dưới đây sử dụng **Node.js** và thư viện chuẩn; không cần thư viện parser bên ngoài.

Tạo `modulith-to-mermaid.cjs` trong **dự án thực hành**:

~~~javascript
// Chạy: node modulith-to-mermaid.cjs modulith.json > module-graph.mmd
const fs = require("node:fs");

if (process.argv.length !== 3) {
  console.error("Usage: node modulith-to-mermaid.cjs modulith.json");
  process.exit(2);
}

const data = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
if (!data || typeof data !== "object" || Array.isArray(data)) {
  throw new Error("JSON root phải là object chứa application modules");
}

const names = Object.keys(data).sort();
if (names.length === 0) {
  throw new Error("Không có module trong JSON");
}

// Tránh dùng trực tiếp tên kỹ thuật làm cú pháp Mermaid.
const ids = new Map(names.map((name, index) => [name, "m" + index]));
const allowedTypes = new Set([
  "DEFAULT", "USES_COMPONENT", "EVENT_LISTENER"
]);

function safeLabel(value) {
  // Giữ chữ Unicode và ký tự đơn giản; loại metacharacter của Mermaid.
  return String(value)
    .replace(/[^\p{L}\p{N}\p{M} ._()-]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const lines = ["flowchart LR"];

// Khai báo mọi node, kể cả module độc lập.
for (const name of names) {
  const module = data[name];
  if (!module || typeof module !== "object" || Array.isArray(module)) {
    throw new Error("Module không hợp lệ: " + name);
  }
  if (!Array.isArray(module.dependencies)) {
    throw new Error("Thiếu mảng dependencies của " + name);
  }

  const label = safeLabel(module.displayName || name) || "Module";
  lines.push('  ' + ids.get(name) + '["' + label + '"]');
}

// Sinh cạnh từ module hiện tại tới module đích.
for (const source of names) {
  const byTarget = new Map();
  for (const dep of data[source].dependencies) {
    if (!dep || typeof dep.target !== "string") {
      throw new Error("Dependency không hợp lệ trong " + source);
    }
    if (!ids.has(dep.target)) {
      throw new Error("Target không tồn tại: " + source + " -> " + dep.target);
    }
    if (!Array.isArray(dep.types) || dep.types.length === 0) {
      throw new Error("Thiếu types: " + source + " -> " + dep.target);
    }

    if (!byTarget.has(dep.target)) {
      byTarget.set(dep.target, new Set());
    }
    for (const type of dep.types) {
      if (!allowedTypes.has(type)) {
        throw new Error("Dependency type chưa được hỗ trợ: " + type);
      }
      byTarget.get(dep.target).add(type);
    }
  }

  for (const target of [...byTarget.keys()].sort()) {
    const types = [...byTarget.get(target)].sort().join(", ");
    lines.push(
      "  " + ids.get(source) + " -->|" + types + "| " + ids.get(target)
    );
  }
}

console.log(lines.join("\n"));
~~~

Mã nguồn trên có một số điểm đáng chú ý:

- **Validate root và module:** nếu JSON không theo schema đang mong đợi, dừng với thông báo lỗi. Không suy diễn một trang lỗi thành sơ đồ.
- **Không bỏ module cô lập:** tạo tất cả nút trong vòng lặp đầu tiên, sau đó mới tạo cạnh.
- **Giữ chiều dependency:** mỗi cạnh được viết dưới dạng ID của `source` đến ID của `dep.target`.
- **Đối chiếu `target`:** nếu JSON tham chiếu đến module không tồn tại, báo lỗi để người dùng kiểm tra snapshot thay vì vẽ nút không có metadata.
- **Gộp nhãn types:** một cặp source/target chỉ có một cạnh; các loại quan hệ khác nhau được gom vào một tập rồi sắp xếp.
- **ID ổn định:** sắp xếp tên kỹ thuật để đầu ra tương đối dễ đọc diff. Không dùng nhãn hiển thị làm khóa.
- **Bảo vệ cú pháp nhãn:** `safeLabel` loại một số ký tự điều khiển Mermaid. Nếu cần giữ dấu đặc biệt, có thể mở rộng escape theo phiên bản Mermaid; không thay đổi khóa nội bộ khi làm sạch nhãn.

Chạy lệnh:

~~~bash
node modulith-to-mermaid.cjs modulith.json > module-graph.mmd
~~~

Với JSON mục 4, nội dung `module-graph.mmd` sẽ là:

~~~mermaid
flowchart LR
  m0["Inventory"]
  m1["Notification"]
  m2["Ordering"]
  m3["Payment"]
  m4["Reporting"]
  m1 -->|EVENT_LISTENER| m2
  m2 -->|USES_COMPONENT| m0
  m2 -->|DEFAULT, USES_COMPONENT| m3
~~~

Thứ tự và ID nút do script sinh ra không ảnh hưởng đến ngữ nghĩa. Kết quả vẫn là **5 nút, 3 cặp cạnh có hướng, 4 nhãn loại quan hệ** (trong đó một cạnh mang hai loại).

## 7. Kết xuất đồ thị để chèn vào tài liệu

Có thể dùng trực tiếp khối code Mermaid trong Markdown hỗ trợ Mermaid. Nếu cần ảnh SVG để gửi kèm tài liệu, dùng Mermaid CLI trong môi trường đã có Node.js và được phép cài công cụ:

~~~bash
npx --yes @mermaid-js/mermaid-cli -i module-graph.mmd -o module-graph.svg
~~~

Nếu đã cài CLI và lệnh `mmdc` có sẵn, có thể dùng `mmdc -i module-graph.mmd -o module-graph.svg`. Với pipeline CI nên ghim phiên bản Mermaid CLI, vì renderer mới có thể bố trí nút khác dù dữ liệu không thay đổi.

Khi sơ đồ chứa package và quan hệ nội bộ nhạy cảm, ưu tiên kết xuất cục bộ hoặc trong CI; tránh tải JSON production lên công cụ online không được đơn vị quản trị cho phép.

Ngoài Mermaid, có thể thể hiện cùng một graph bằng Graphviz DOT:

~~~dot
digraph Modules {
    rankdir=LR;
    inventory [label="Inventory"];
    notification [label="Notification"];
    ordering [label="Ordering"];
    payment [label="Payment"];
    reporting [label="Reporting"];

    notification -> ordering [label="EVENT_LISTENER"];
    ordering -> inventory [label="USES_COMPONENT"];
    ordering -> payment [label="DEFAULT, USES_COMPONENT"];
}
~~~

Graphviz phù hợp nếu hệ thống đã có công cụ `dot` hoặc cần kiểm soát bố cục chi tiết. Dù dùng định dạng nào, **tập nút/cạnh phải nhất quán với JSON**.

## 8. Module lồng nhau và sơ đồ nhiều cấp

Một số ứng dụng sử dụng *nested application module*. Schema Spring Modulith có thể có `parent` hoặc `nested` để biểu diễn quan hệ module cha/con.

Khi muốn biểu diễn phân cấp trong Mermaid, có thể sử dụng `subgraph`:

~~~mermaid
flowchart LR
    subgraph commerce["Commerce"]
        ordering["Ordering"]
        checkout["Checkout"]
    end
    payment["Payment"]
    checkout -->|"USES_COMPONENT"| payment
~~~

Ở ví dụ này, `Commerce` là nhóm trực quan. **Quan hệ chứa không phải dependency.** Không tự sinh cạnh `commerce → checkout` hoặc `ordering → checkout` chỉ vì module được lồng vào một nhóm. Muốn xây dựng subgraph tự động, phải kiểm tra cấu trúc thực tế của `parent` và `nested` ở phiên bản Spring Modulith đang dùng.

Script ở mục 6 chủ động dựng **dependency graph phẳng**. Việc chưa nhóm theo `parent` không làm mất những cạnh dependency, nhưng nếu có cấu trúc lồng nhau thì đồ thị chưa thể hiện thông tin phân cấp. Khi mở rộng script, nên giữ riêng hai lớp thông tin: **containment** và **dependency**.

Đối với hệ thống có hàng chục module, một graph toàn cục có thể khó đọc. Có thể tạo thêm đồ thị con cho module trọng tâm hoặc lọc cạnh theo `types`. Nếu áp dụng bộ lọc, cần ghi rõ bộ lọc để người đọc không nhầm sơ đồ đã lọc với toàn bộ kiến trúc.

## 9. Kiểm chứng kết quả và so sánh qua các bản triển khai

Một tệp Mermaid render thành công vẫn có thể sai ý nghĩa. Hãy kiểm tra:

| Điều cần xác minh | Cách kiểm tra |
| --- | --- |
| **Số nút** | Bằng số khóa module cấp cao trong JSON, kể cả module không có cạnh. |
| **Cạnh có hướng** | Với mỗi `source.dependencies[].target` phải có `source → target`. |
| **Loại phụ thuộc** | Giữ mọi phần tử `types[]`, không chỉ phần tử đầu tiên. |
| **Định danh đích** | Mọi `target` phải trỏ đến một module được công bố. |
| **Quan hệ phân cấp** | Nếu hiển thị `parent`/`nested`, không biến chúng thành dependency giả. |
| **Nhân bản cùng cặp** | Có thể gộp nhiều loại quan hệ vào một cạnh nếu ghi rõ nhãn. |
| **Thứ tự đầu ra** | Có thứ tự ổn định để xem diff dễ dàng. |

Đối với JSON mẫu, đáp án kiểm chứng là **5 nút và 3 cạnh**. Nếu chỉ thấy 4 nút, nhiều khả năng script bỏ `reporting`. Nếu cạnh `notification → ordering` bị đảo chiều, script đã hiểu nhầm event flow với dependency.

Để so sánh các bản phát hành, lưu snapshot hợp lệ của endpoint theo phiên bản rồi sinh `module-graph.mmd` cho từng snapshot. So sánh **tập tên module, tập cạnh nguồn/đích và các loại quan hệ** sẽ đáng tin cậy hơn so sánh ảnh SVG theo vị trí pixel; renderer có thể sắp xếp khác mà kiến trúc không đổi.

Khi graph cho thấy một quan hệ không mong muốn, hãy kiểm tra mã nguồn và sử dụng `ApplicationModules.verify()` trong test/CI để xác định vi phạm phụ thuộc vòng, truy cập vào phần internal hoặc giới hạn dependency đã khai báo. Bản đồ từ Actuator giúp **quan sát cấu trúc** nhưng không thay thế phép **kiểm chứng quy tắc kiến trúc**.

## 10. Sự cố thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `/actuator/modulith` trả 404 | Thiếu Spring Modulith Actuator, chưa expose endpoint, sai cổng/base path hoặc endpoint không có quyền truy cập. | Xem dependency, cấu hình exposure/access và đường dẫn thực tế. |
| Trả 401/403 | Endpoint có xác thực hoặc phân quyền. | Dùng thông tin truy cập hợp lệ, không tắt bảo mật chỉ để lấy JSON. |
| Parser không đọc được JSON | Tệp chứa trang HTML đăng nhập hoặc thông báo lỗi. | Kiểm tra HTTP status và nội dung response trước khi chạy script. |
| Script báo `target` không tồn tại | JSON không đồng nhất, bị sửa hoặc schema khác dự kiến. | So khớp `dependencies[].target` với khóa module cấp cao. |
| Module có `dependencies: []` không xuất hiện | Chỉ vẽ nút khi duyệt cạnh. | Tạo danh sách nút riêng trước khi sinh cạnh. |
| Mũi tên bị ngược | Nhầm dependency với luồng sự kiện. | Vẽ module hiện tại → `target`, kể cả `EVENT_LISTENER`. |
| Thiếu loại quan hệ trên cạnh | Chỉ lấy `types[0]`. | Duyệt và gộp toàn bộ mảng `types[]`. |
| Renderer Mermaid lỗi | ID hoặc nhãn chứa ký tự đặc biệt, cú pháp sai. | Sinh ID an toàn, kiểm tra escape nhãn và cú pháp phiên bản renderer. |
| Sơ đồ khác với hình từ `Documenter` | Khác định dạng, bộ lọc, cấu hình nhận diện hoặc version chạy. | Đối chiếu tập dependency dưới cùng điều kiện, không chỉ so hình. |
| Không tìm thấy lời gọi trong trace dù graph có cạnh | Graph tĩnh không đồng nghĩa request thực sự đi qua cạnh; sampling hoặc context propagation cũng ảnh hưởng trace. | Kiểm tra đường thực thi, instrumentation, tracing backend và cấu hình truyền context. |

## 11. Quan hệ với `Documenter`, metrics và traces

Spring Modulith có sẵn **`Documenter`** để sinh sơ đồ C4/UML và Module Canvas từ mô hình `ApplicationModules` trong mã nguồn/test. Đó thường là lựa chọn phù hợp khi tạo tài liệu kiến trúc từ source. Còn cách chuyển JSON endpoint thành Mermaid tập trung vào **cấu trúc mà phiên bản ứng dụng đang chạy công bố**, nên hữu ích cho kiểm tra triển khai, snapshot môi trường và công cụ nội bộ.

| Nguồn | Câu hỏi trả lời |
| --- | --- |
| `ApplicationModules` / `Documenter` | Mã nguồn chia module và quan hệ như thế nào? Cần tài liệu kiến trúc gì? |
| `/actuator/modulith` | Bản chạy hiện tại nhận diện những module và dependency nào? |
| `ApplicationModules.verify()` | Các quan hệ có tuân thủ những quy tắc kiến trúc được kiểm tra không? |
| Event metrics | Những sự kiện được instrument được phát với tần suất bao nhiêu? |
| Traces với context propagation | Request hoặc luồng xử lý được quan sát đã đi qua những chặng nào? |

Một cạnh `ordering → inventory` không tự chứng minh mọi request đặt hàng đều gọi inventory. Muốn phân tích một request cụ thể cần trace/log; muốn xem xu hướng cần metrics; muốn xác định phụ thuộc sai cần kiểm thử kiến trúc.

## 12. Bài tập và câu hỏi tự kiểm tra

**Bài tập 1.** Từ JSON mục 4, vẽ một sơ đồ bằng tay và xác nhận có 5 nút, 3 cạnh. Giải thích tại sao `reporting` vẫn phải xuất hiện.

**Bài tập 2.** Thêm module `audit` với `dependencies: []`. Chạy lại script: phải xuất hiện thêm nút nhưng không có cạnh mới.

**Bài tập 3.** Đổi `ordering.dependencies[0].target` thành `stock` mà không thêm module `stock`. Script phải báo lỗi thay vì vẽ một nút chưa có metadata.

**Bài tập 4.** Thêm một phần tử dependency khác từ `ordering` đến `payment` với `types: ["EVENT_LISTENER"]`. Script phải gộp các loại quan hệ vào một cạnh `ordering → payment`, không đảo chiều.

**Bài tập 5.** Lấy hai snapshot từ hai bản triển khai được phép truy cập. Liệt kê node và dependency mới/thay đổi, rồi kiểm tra xem đó là thay đổi dự kiến hay cần điều tra.

**Câu hỏi 1:** Vì sao nên dùng khóa module, thay vì `displayName`, để nối cạnh? Vì `displayName` có thể trùng hoặc chứa ký tự khó dùng làm ID; khóa kỹ thuật được tham chiếu trực tiếp bởi `target`.

**Câu hỏi 2:** Vì sao không dùng `EVENT_LISTENER` để suy ra chiều event nghiệp vụ? Vì loại này mô tả quan hệ phụ thuộc mã nguồn do listener, không phải dữ liệu thời gian chạy hay chiều publish một cách đầy đủ.

**Câu hỏi 3:** Có thể biết module nào đang lỗi dựa trên module graph không? Không. Cần thêm health, logs, metrics hoặc traces theo loại sự cố.

**Câu hỏi 4:** Vì sao sinh sơ đồ từ endpoint không thay thế `ApplicationModules.verify()`? Vì sơ đồ chỉ trình bày quan hệ; `verify()` thực thi kiểm tra các quy tắc kiến trúc.

## 13. Tài liệu tham khảo

- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): endpoint `modulith`, schema JSON và các loại dependency.
- [Spring Modulith — Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html): sinh sơ đồ C4/UML và Module Canvas bằng `Documenter`.
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): `ApplicationModules.verify()` và kiểm tra ranh giới.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): expose và bảo vệ endpoint.
- [Mermaid — Flowcharts](https://mermaid.js.org/syntax/flowchart.html): cú pháp node, cạnh và `subgraph`.
- [Mermaid CLI](https://github.com/mermaid-js/mermaid-cli): kết xuất Mermaid thành SVG/PNG.

**Ghi nhớ:** khi vẽ module graph từ `/actuator/modulith`, phải bảo toàn **đủ module**, **đúng chiều phụ thuộc** và **toàn bộ các loại quan hệ**. Dùng ID an toàn để sinh sơ đồ ổn định, xem `parent`/`nested` là phân cấp thay vì dependency, và kết hợp với kiến trúc test cùng metrics/traces khi cần đánh giá hệ thống trong vận hành.
