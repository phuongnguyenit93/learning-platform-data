# Cấu hình phạm vi được dệt và phạm vi bị loại trừ

## 1. Vì sao cấu hình weaving scope là quyết định kiến trúc?

Trong **Aspect-Oriented Programming (AOP)**, **weaving** là quá trình kết hợp hành vi của aspect/advice với mã chương trình tại những điểm mà một cơ chế hỗ trợ. Có nhiều cách hiện thực: biến đổi mã nguồn hoặc biểu diễn trung gian khi build, biến đổi bytecode tại lúc biên dịch hoặc nạp lớp, runtime instrumentation, hoặc một hình thức interception khác. Không phải mọi hệ thống AOP đều biến đổi bytecode; những kỹ thuật proxy/wrapper cũng có phạm vi quan sát riêng.

Trong một ứng dụng có hàng nghìn class, thông thường ta **không muốn tất cả đều là đối tượng bị weaving**. Những module chứa business operation có thể cần logging, tracing hoặc policy kỹ thuật; trong khi thư viện framework, infrastructure, mã instrumentation, generated code, class loader, security internals hay thư viện bên thứ ba có thể cần tránh biến đổi hoặc ít nhất cần được xem xét rất thận trọng.

Câu hỏi cốt lõi:

> **Mã nào được phép trở thành ứng viên cho weaving, mã nào nhất định bị loại, và làm sao chứng minh artifact đang chạy thực sự tuân thủ chính sách đó?**

Cấu hình không chỉ là tối ưu hóa. Nó ảnh hưởng đến:

- **Tính đúng đắn:** advice có xuất hiện ở đường xử lý cần thiết không?
- **Tính an toàn:** mã quan trọng có nguy cơ bị bỏ qua hoặc bị biến đổi ngoài chủ đích không?
- **Hiệu năng:** công cụ cần quét/biến đổi bao nhiêu class, và advice chạy bao nhiêu lần?
- **Độ ổn định:** có xung đột với mã đã biến đổi, generated code, runtime hoặc classloader khác không?
- **Khả năng bảo trì:** thêm module/class mới có tự động rơi vào scope hay không?
- **Khả năng kiểm chứng:** có log/list/report về các class được weave, không được weave và các join point được chọn không?

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **weaving scope**, **pointcut scope**, **advice applicability** và **runtime call path**.
2. Mô tả các tiêu chí **include**, **exclude**, ranh giới module/package/class/loader/artifact và chính sách ưu tiên loại trừ.
3. Lập chính sách phạm vi theo **allowlist rõ ràng, denylist có chủ đích, default behavior** và quy tắc xung đột được kiểm tra.
4. Hiểu ảnh hưởng của build-time, load-time và runtime instrumentation đối với tập class thật sự được biến đổi.
5. Tránh recursion khi aspect vô tình can thiệp chính logger, metric sink hoặc đoạn mã hỗ trợ weaving.
6. Phân tích giới hạn khi có interface, subclass, annotation, generated classes, nested classes, classloader, dependency, module boundaries hoặc mã đã được load.
7. Xây dựng thử nghiệm positive/negative, kiểm tra artifact thực, đọc diagnostic và theo dõi thay đổi scope sau refactor.
8. Chạy ví dụ Java 17 minh họa quy tắc **include/exclude** bằng một proxy nhỏ, đồng thời hiểu vì sao minh họa đó **không phải trình dệt bytecode**.

Nội dung nói về **AOP nói chung**. Không đưa cú pháp riêng của một engine thành chuẩn áp dụng cho mọi công nghệ.

## 2. Bốn tầng quyết định một advice có xuất hiện hay không

Một lời khuyên “pointcut đã đúng thì advice sẽ chạy” là chưa đủ. Ta phải phân biệt bốn tầng.

### 2.1. Tầng 1 — Phạm vi được xét để weaving (*weaving eligibility*)

Công cụ có thể chỉ được cấu hình xét các class trong một module, package, archive, classloader hoặc những artifact được đưa qua bước biến đổi. Một class nằm ngoài scope có thể **không được công cụ biến đổi**, bất kể tên method hay annotation của nó.

Ví dụ giả mã:

```text
include classes under application.orders
exclude classes under application.instrumentation
exclude classes under application.generated
```

Nếu class `vendor.PaymentClient` không thuộc include, các method của nó **không trở thành đối tượng weaving theo cấu hình đó**, ngay cả khi tên `pay` khớp một pointcut rộng.

### 2.2. Tầng 2 — Tập join point mà engine hỗ trợ

Ngay cả khi class được xét, một engine có thể chỉ hỗ trợ **method execution**; một engine khác hỗ trợ cả method call, constructor, field get/set hoặc handler join point. Ví dụ, annotation trên field không khiến interface proxy tự bắt thao tác ghi field.

Scope là điều kiện **có đủ tư cách để được xét**, không phải sự bảo đảm rằng mọi thao tác trong class đều có hook.

### 2.3. Tầng 3 — Pointcut và điều kiện của advice

Trong class nằm trong scope, pointcut có thể chỉ khớp một số method có marker, chữ ký, modifier hoặc runtime context phù hợp. Nhiều class hợp lệ có thể không có join point nào được chọn.

Ví dụ:

```text
eligible class: app.orders.OrderService
pointcut: execution of methods with marker "Observed"

methods:
  createOrder()  [Observed] -> pointcut có thể khớp
  toString()     [không có]  -> không khớp
```

### 2.4. Tầng 4 — Đường chạy thực tế (*runtime occurrence*)

Một class đã weave và pointcut đã chọn vẫn không đồng nghĩa advice phải chạy ngay. Nhánh code có thể không được thực hiện, điều kiện runtime có thể sai, hoặc ở một mô hình proxy lời gọi có thể **đi thẳng vào target**.

Mô hình tư duy:

```text
Tất cả mã / artifact đang có
         |
         v
Lọc include/exclude ở tầng weaving
         |
         v
Những đơn vị đủ điều kiện để biến đổi
         |
         v
Join points thuộc loại công cụ hỗ trợ
         |
         v
Các điểm pointcut/advice thực sự khớp
         |
         v
Mỗi occurrence thực sự xảy ra ở runtime
         |
         v
Advice được kích hoạt theo hợp đồng engine
```

**Không thể dùng log advisor hoặc danh sách class đã weave làm bằng chứng duy nhất rằng từng runtime path đã được bao phủ.** Ngược lại, không thể dùng một test không chạy đến method để kết luận weaving không hoạt động.

## 3. Phân biệt ba loại “scope” dễ bị dùng lẫn

| Loại scope | Ví dụ | Ai quyết định? | Nếu sai có thể xảy ra |
| --- | --- | --- | --- |
| **Weaving scope** | Chỉ biến đổi class trong `app.billing`, bỏ `app.generated`. | Build tool, transformer, agent, classloader/engine config. | Class mong muốn không weave; class không mong muốn bị weave. |
| **Pointcut scope** | Chọn execution của method được marker `@Audited`. | Biểu thức/API matcher của pointcut. | Advice quá rộng hoặc quá hẹp trong vùng eligible. |
| **Runtime/interception scope** | Chỉ lời gọi thông qua object proxy. | Cách lắp object, call path, runtime weaving. | Caller bypass proxy hoặc điểm không bao giờ xảy ra. |

Khi viết tài liệu kỹ thuật, không chỉ nói “scope của aspect”. Nên viết rõ: **“scope được đưa qua weaving”**, **“scope pointcut”** hay **“đường runtime đi qua hook”**.

### 3.1. Phạm vi của chính aspect và phạm vi target không giống nhau

Một cấu hình có thể lựa chọn:

- Những **target classes** có thể bị can thiệp.
- Những **aspect classes** được đăng ký và có advice hoạt động.
- Những **dependency artifacts** được đưa qua bước biến đổi.
- Những **join point kinds** được engine hỗ trợ hoặc bật.

Một aspect được tải/đăng ký **không** có nghĩa tất cả target của nó đã weave. Ngược lại, một class target đủ điều kiện được weave nhưng không có aspect/pointcut nào khớp cũng có thể không phát sinh advice.

### 3.2. Phần “bị loại trừ” có thể nằm ở tầng khác

Một exclude ở **transformer** có thể chặn công cụ biến đổi class. Một `NOT package(internal)` trong **pointcut** chỉ lọc join point của advice đã khai báo. Kết quả giống nhau trong một ca test cụ thể không có nghĩa hai chính sách tương đương.

Nếu class không được weave thì mọi aspect phụ thuộc vào weaving của engine trên class đó có thể không tác động được. Nếu chỉ loại nó khỏi **một pointcut**, những pointcut khác vẫn có thể chọn class đó.

## 4. Include: tạo danh sách được phép (*allowlist*)

Trong các ứng dụng lớn, chiến lược an toàn thường bắt đầu từ một **positive scope** rõ ràng.

Ví dụ giả mã:

```text
weaving:
  include:
    - app.orders.*
    - app.billing.*
    - shared.applicationapi.*
```

Các dấu `*` chỉ mang tính mô tả. Một công cụ có thể dùng tên package, biểu thức kiểu, pattern của tên file/class, resource path, regular expression hoặc cấu hình khác. Cần xác nhận **kỹ thuật matching và nghĩa của wildcard** trong công cụ thực.

### 4.1. Chọn theo package/namespace

Ưu điểm:

- Ranh giới tương đối dễ đọc và review.
- Mở rộng theo các lớp mới trong cùng miền.
- Dễ tổ chức trách nhiệm giữa team/module.

Rủi ro:

- Refactor đổi package làm class rời scope.
- Một package có thể chứa cả business code và helper nên cần loại trừ thêm.
- Tên package trong source không phải lúc nào trùng với đường resource/descriptor mà transformer nhận.

### 4.2. Chọn theo module hoặc artifact

Trong hệ thống chia module, đôi khi chính sách phù hợp là **chỉ weave module application** mà không weave external dependencies. Cấu hình ở tầng build thường có thể biết artifact nào được xử lý; runtime classloader cũng có thể đóng vai trò ranh giới.

Cần xác định những dependency nào là **nguồn cần can thiệp thực sự**. Nếu một policy phải quan sát lời gọi nằm trong dependency cụ thể, exclude toàn bộ thư viện bên thứ ba có thể làm thiếu độ phủ. Nếu không cần, việc mặc định weave tất cả dependencies tăng nguy cơ xung đột và chi phí kiểm thử.

### 4.3. Chọn theo class hoặc annotation

Một số công cụ cho phép match class theo kiểu, marker hoặc metadata. Chẳng hạn:

```text
include types with annotation "Weavable"
```

Nhưng annotation chỉ là metadata. Nó phải được đọc ở thời điểm thích hợp, ở declaration thích hợp, và công cụ phải hỗ trợ tiêu chí ấy ở **weaving scope** chứ không chỉ ở pointcut.

Nếu một annotation chỉ có `SOURCE` retention, runtime reflection không thể đọc nó như marker `RUNTIME`. Một công cụ phân tích source trước compile có thể dùng nó; công cụ chỉ đọc runtime class có thể không.

## 5. Exclude: loại trừ có chủ đích (*denylist*)

Một cấu hình include có thể bao trùm nhiều class hợp lý nhưng cần loại trừ những vùng có rủi ro.

Ví dụ:

```text
weaving:
  include:
    - app.*
  exclude:
    - app.instrumentation.*
    - app.generated.*
    - app.bootstrap.*
```

Một chính sách thực tế phải nói rõ:

- **Exclude được áp trước hay sau include?**
- Nếu một class khớp cả hai thì **rule nào thắng**?
- Nếu không khớp include nào thì mặc định gì?
- Có khác nhau giữa exclude ở **build tool**, **classloader**, **transformer** và **pointcut** không?
- Có hỗ trợ nested classes hoặc generated methods không?
- Một rule trong module cha có thể bị module con override không?

Không có mặc định **“deny luôn thắng”** áp dụng cho mọi công cụ. Tuy nhiên, bạn có thể chọn **deny-overrides** làm **chính sách thiết kế nội bộ**, rồi bảo đảm engine/config hiện thực đúng theo tài liệu và test.

### 5.1. Những nhóm thường cân nhắc loại trừ

| Nhóm | Vì sao cần xem xét | Có bắt buộc luôn exclude? |
| --- | --- | --- |
| Logger, metrics exporter, tracing internals | Tránh advice gọi lại chính công cụ quan sát, gây recursion hoặc overhead không kiểm soát. | Không tuyệt đối; có thể đặt hook khác, nhưng cần tách lớp rõ. |
| Code sinh tự động / synthetic / bridge | Code có thể đổi theo compiler, nhiều method không hiện trên source và có khả năng tạo trùng tín hiệu. | Không; đôi khi generated code là điểm cần đo. |
| Bootstrap / khởi tạo hạ tầng | Biến đổi quá sớm có thể tạo phụ thuộc vòng hoặc lỗi classloading. | Tùy khả năng engine và mục tiêu. |
| Dependencies của bên thứ ba | Dễ gặp xung đột phiên bản/bytecode, scope quá rộng. | Không; có ca cần instrument dependency. |
| Proxy/helper do công cụ sinh | Tránh weave chồng hoặc recursion ngoài chủ đích. | Phụ thuộc engine và cách tạo helper. |
| Test fixtures | Có thể làm test phức tạp và kém ổn định. | Tùy việc muốn test weaving thật hay logic thuần. |
| Thành phần bí mật/nhạy cảm | Advice log args/results có thể làm lộ dữ liệu. | Không nên dựa vào exclude thay cho data minimization/security policy. |
| Package cực kỳ nóng | Advice có thể tăng overhead nhiều lần. | Cần benchmark; có thể giảm pointcut thay vì exclude toàn bộ. |

**Không tự động loại trừ mọi thành phần “internal” nếu những thao tác đó là yêu cầu audit hoặc bảo mật bắt buộc.** Exclude là quyết định phạm vi, cần có lý do và người chịu trách nhiệm.

### 5.2. Exclude để ngăn vòng lặp recursion

Giả sử advice thực hiện:

```text
businessMethod()
  -> advice before
      -> metrics.record()
          -> advice before
              -> metrics.record()
                  -> ...
```

Nếu `metrics.record()` cũng thuộc target weave và được cùng pointcut chọn, hệ thống có thể rơi vào recursion/reentrancy. Một giải pháp là tách module `instrumentation` và loại nó ở tầng weaving hoặc pointcut phù hợp.

Nhưng phải hiểu: **loại helper khỏi weaving** có thể làm giảm các hook khác trên helper. Nếu chỉ muốn ngăn một advice nhất định, exclude trong pointcut của advice đó có thể chính xác hơn. Hãy chọn tầng có **phạm vi tác động nhỏ nhất đủ đạt mục tiêu**.

### 5.3. Exclude không phải “tắt bảo mật”

Nếu một aspect được dùng cho kiểm tra quyền truy cập, thêm exclude cho một package mới có thể vô tình tạo đường bypass. Chính sách authorization quan trọng phải có biên tin cậy và invariant đáng tin, không chỉ dựa vào một transformer được cấu hình đúng. Mỗi thay đổi exclude cần qua đánh giá ảnh hưởng đến bảo mật và những điểm cần audit.

## 6. Thứ tự và xung đột giữa include/exclude

Xét các rule:

```text
include app.*
exclude app.internal.*
include app.internal.reports.*
```

Một class `app.internal.reports.MonthlyReport` khớp **cả ba**. Kết quả là gì? Không thể trả lời nếu thiếu hợp đồng về rule precedence của công cụ.

Có ít nhất ba mô hình có thể được định nghĩa:

1. **Deny-overrides:** bất kỳ exclude nào khớp thì loại, bất kể include khác.
2. **Last-match wins:** rule cuối cùng khớp quyết định.
3. **Specificity/order-based:** rule chi tiết hơn hoặc độ ưu tiên được khai báo quyết định.

Những mô hình này tạo kết quả khác nhau. Không đoán chỉ từ thứ tự dòng YAML/JSON hoặc tên pattern. Phải đọc hợp đồng hoặc chạy test cho chính công cụ đã chọn.

### 6.1. Một chính sách dễ kiểm chứng

Nếu có quyền thiết kế lớp cấu hình, có thể định nghĩa:

```text
eligible(type) =
    matchesAtLeastOneInclude(type)
    AND NOT matchesAnyExclude(type)
```

Tức **allowlist + deny-overrides**. Với một type không khớp include nào, `eligible=false`. Đây là **chính sách trong bài học**, không khẳng định mọi engine dùng cùng công thức.

| Khớp include? | Khớp exclude? | Eligible theo policy trên |
| --- | --- | --- |
| Không | Không | Không |
| Không | Có | Không |
| Có | Không | **Có** |
| Có | Có | **Không** |

Bảng này nên trở thành một unit test cho lớp chọn scope. Nếu một công cụ dùng mô hình khác, điều chỉnh cấu hình hoặc wrapper để đạt chính sách mong muốn và ghi lại khác biệt.

### 6.2. “Tập eligible” chưa bằng “tập advice chạy”

Giả sử class `app.billing.InvoiceService` eligible. Nếu pointcut chỉ chọn method có `@Tracked` mà `invoicePreview()` không có marker, method ấy không được advice xử lý. Ngược lại, `app.internal.SyncService` có marker nhưng exclude ở tầng weaving thì advice dùng cơ chế đó không được cài trên class ấy.

Tách hai bài test:

- **Scope test:** class có được phép đi qua weaving không?
- **Pointcut/runtime test:** join point trên class đủ điều kiện có thực sự được chọn/kích hoạt khi chạy không?

## 7. Cấu hình mẫu ở mức kiến trúc (không gắn với engine)

Giả sử một hệ thống có module:

```text
app/
  orders/
  billing/
  internal/
    monitoring/
    bootstrap/
  generated/
  cli/
external/
  paymentclient/
  serializer/
```

Mục tiêu: weave application business code ở `orders` và `billing`; không weave nội bộ monitoring, generated classes hoặc dependencies bên ngoài. Mẫu **giả mã cấu hình**:

```yaml
weaving:
  eligible:
    include:
      - "app.orders.**"
      - "app.billing.**"
    exclude:
      - "app.internal.**"
      - "app.generated.**"
  policy:
    default: deny
    conflict: deny-overrides
```

Đây **không phải file cấu hình dùng trực tiếp** của một công cụ; khóa `eligible`, `policy`, `conflict` và wildcard chỉ giúp mô tả yêu cầu. Engine có thể yêu cầu property, XML, Java API, build-plugin DSL, regex, package descriptor hoặc trình biến đổi riêng.

### 7.1. Cần tách cấu hình người viết và cấu hình engine hiểu

Khi dịch policy sang config cụ thể, kiểm tra:

- Engine dùng **tên class đầy đủ** hay đường resource?
- Wildcard `*` có khớp dấu chấm/package delimiter không? `**` được hiểu thế nào?
- Rule xét interface, implementation hay cả hai?
- Có include/exclude ở tầng **aspect registration** riêng không?
- Có thể cấu hình từng **archive/module** ngoài từng class không?
- Rule từ file cấu hình và rule truyền qua command line/agent có độ ưu tiên ra sao?
- Cấu hình bị khóa lúc build hay còn có thể đổi ở runtime?
- Thông báo “matched” đang nói scope class hay pointcut advice?

Một config nhìn hợp lý nhưng regex/wildcard khác kỳ vọng có thể bỏ qua hàng loạt class. Hãy xây **bảng các tên class mẫu và kết quả dự kiến** trước khi tin rằng wildcard đã đúng.

## 8. Build-time, load-time và runtime: scope được áp ở đâu?

### 8.1. Weaving lúc build hoặc compile

Một công cụ có thể biến đổi source/bytecode rồi đóng gói artifact. Phạm vi weaving lúc đó phụ thuộc:

- Danh sách file/class được đưa qua bước biến đổi.
- Source set, module, dependency artifacts trong build graph.
- Phiên bản compiler/transformer và thứ tự plugin.
- Incremental build, cache, generated classes hoặc mã từ dependency.
- Việc artifact đang chạy **có đúng là artifact đã được biến đổi**.

**Rủi ro:** thay đổi cấu hình mà không rebuild/redeploy artifact đúng có thể khiến người kiểm thử tưởng exclude đã hoạt động trong khi binary cũ vẫn được dùng.

### 8.2. Weaving lúc nạp lớp (load-time)

Một class transformer/classloader có thể xem xét từng class khi chúng được nạp. Scope lúc đó còn phụ thuộc:

- Loader nào áp transformer và loader nào không.
- Class có được load **trước khi** transformer kích hoạt hay không.
- Module system, khả năng truy cập class và những giới hạn runtime.
- Thứ tự giữa nhiều transformer/agent.
- Class được tạo động hoặc nạp trong loader riêng.

Một pattern include theo tên class có thể đúng nhưng transformer không hề nhìn thấy class của loader khác. Không nên báo “scope khớp” chỉ dựa vào tên package nếu hệ thống dùng nhiều classloader.

### 8.3. Runtime instrumentation/retransformation

Một số cơ chế cho phép instrument/retransform class khi runtime đang hoạt động, nhưng khả năng này **có giới hạn**, phụ thuộc API, định dạng class, kiểu thay đổi và quyền runtime. Không thể mặc định mọi class đã nạp đều có thể biến đổi mọi mặt hoặc chuyển về nguyên trạng chỉ bằng đổi cấu hình.

Nếu update exclude trong lúc đang chạy, câu hỏi quan trọng là:

- **Những class trước đây đã weave có tự được hoàn nguyên không?**
- **Class mới load có dùng policy mới không?**
- **Những invocation đang chạy bị ảnh hưởng thế nào?**

Câu trả lời không có giá trị chung cho mọi engine. Với cấu hình production, nên xem thay đổi weaving scope như **thay đổi artifact/runtime behavior cần rollout và rollback plan**, không phải thay một flag vô hại.

### 8.4. Proxy/wrapper: scope nằm ở nơi đối tượng được bọc

Một interface proxy có thể quyết định tạo wrapper cho một target hay trả target nguyên gốc. Điều này minh họa allowlist/exclude ở một tầng, nhưng **không phải bytecode weaving**. Một method của class được bọc có thể vẫn được gọi trực tiếp qua reference target ban đầu.

Trong thiết kế proxy, cần kiểm tra:

- Ai tạo target và ai đưa proxy cho caller?
- Caller có giữ tham chiếu gốc không?
- Self-invocation có vòng qua proxy không?
- Class/method visibility và interface boundaries có phù hợp không?
- Có hai proxy lồng nhau khiến advice chạy hai lần không?

Không áp nguyên những giới hạn trên cho mọi kiểu weaving source/bytecode.

## 9. Java 17 runnable: mô phỏng bộ lọc scope bằng proxy

Ví dụ dùng **Java chuẩn**, một allowlist/denylist đơn giản và **JDK dynamic proxy**. Nó **không thực hiện source/bytecode weaving**; chỉ minh họa cách cấu hình **eligible scope** quyết định có tạo proxy/interception cho một đối tượng hay không.

Chính sách trong demo:

```text
include: app.*  OR shared.api
exclude: app.internal.* OR app.generated.*
default: deny
conflict: exclude overrides include
```

Tạo tệp **`WeavingScopeDemo.java`**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class WeavingScopeDemo {
    interface Service {
        String run(String id);
    }

    static final class BillingService implements Service {
        @Override
        public String run(String id) {
            System.out.println("TARGET billing " + id);
            return "BILL:" + id;
        }
    }

    static final class HealthService implements Service {
        @Override
        public String run(String id) {
            System.out.println("TARGET health " + id);
            return "HEALTH:" + id;
        }
    }

    static final class VendorService implements Service {
        @Override
        public String run(String id) {
            System.out.println("TARGET vendor " + id);
            return "VENDOR:" + id;
        }
    }

    static final class GeneratedService implements Service {
        @Override
        public String run(String id) {
            System.out.println("TARGET generated " + id);
            return "GEN:" + id;
        }
    }

    static boolean eligible(String module) {
        boolean included =
                module.startsWith("app.")
                || module.equals("shared.api");
        boolean excluded =
                module.startsWith("app.internal.")
                || module.startsWith("app.generated.");
        return included && !excluded;
    }

    static Service instrument(String module, Service target) {
        if (!eligible(module)) {
            System.out.println("CONFIG excluded " + module);
            return target;
        }
        System.out.println("CONFIG included " + module);

        return (Service) Proxy.newProxyInstance(
                Service.class.getClassLoader(),
                new Class<?>[] { Service.class },
                (proxy, method, args) -> {
                    System.out.println("ADVICE before " + method.getName());
                    try {
                        Object result = method.invoke(target, args);
                        System.out.println("ADVICE returning " + method.getName());
                        return result;
                    } catch (InvocationTargetException ex) {
                        System.out.println("ADVICE throwing " + method.getName());
                        throw ex.getCause();
                    }
                }
        );
    }

    public static void main(String[] args) {
        BillingService originalBilling = new BillingService();

        Service billing = instrument("app.billing", originalBilling);
        Service health = instrument("app.internal.health",
                new HealthService());
        Service vendor = instrument("vendor.adapter",
                new VendorService());
        Service generated = instrument("app.generated.mapper",
                new GeneratedService());

        System.out.println("RESULT " + billing.run("B1"));
        System.out.println("RESULT " + health.run("H1"));
        System.out.println("RESULT " + vendor.run("V1"));
        System.out.println("RESULT " + generated.run("G1"));

        System.out.println("RESULT " + originalBilling.run("DIRECT"));
        System.out.println("CHECK shared.api=" + eligible("shared.api"));
        System.out.println("CHECK app.internal.x="
                + eligible("app.internal.x"));
    }
}
```

Biên dịch và chạy:

```bash
javac WeavingScopeDemo.java
java WeavingScopeDemo
```

Đầu ra dự kiến:

```text
CONFIG included app.billing
CONFIG excluded app.internal.health
CONFIG excluded vendor.adapter
CONFIG excluded app.generated.mapper
ADVICE before run
TARGET billing B1
ADVICE returning run
RESULT BILL:B1
TARGET health H1
RESULT HEALTH:H1
TARGET vendor V1
RESULT VENDOR:V1
TARGET generated G1
RESULT GEN:G1
TARGET billing DIRECT
RESULT BILL:DIRECT
CHECK shared.api=true
CHECK app.internal.x=false
```

### 9.1. Điều gì được minh họa chính xác?

**`app.billing`:** khớp include, không khớp exclude → proxy được tạo. Gọi `billing.run("B1")` đi qua handler nên có advice.

**`app.internal.health`:** tên cũng bắt đầu `app.` nhưng bị exclude cụ thể. Theo policy **exclude thắng**, `instrument` trả target gốc; lời gọi `health.run` không có advice.

**`vendor.adapter`:** không khớp include, nên bị loại theo chính sách **default deny**, dù không có rule exclude cụ thể.

**`app.generated.mapper`:** thuộc include `app.` nhưng exclude theo `app.generated.`, nên không được bọc.

**`shared.api`:** bộ kiểm tra rule trả `true`; demo không tạo instance cho nhánh này. Nó chỉ chứng minh predicate eligible, không chứng minh có target nào thật sự được proxy.

**`originalBilling.run("DIRECT")`:** dù target từng được bọc trong `billing`, caller vẫn giữ tham chiếu tới target gốc nên gọi trực tiếp bypass proxy. Đây là ranh giới **call path** của JDK proxy, không liên quan đến logic eligible đúng/sai.

### 9.2. Điều mà ví dụ không chứng minh

- Không chứng minh bytecode `BillingService` được weave.
- Không chứng minh constructor, field access hoặc internal method call bị can thiệp.
- Không có pointcut DSL hoặc cấu hình transformer/classloader thực.
- Không chứng minh mọi lời gọi tới một class eligible đều có advice.
- Không tự kiểm tra scope của những class generated bởi compiler.
- Không cung cấp module/classloader isolation hoặc hot reload.
- Không thể dùng stdout này để kết luận một công cụ AOP production đã weave đúng artifact.

**Giá trị giáo dục** của demo nằm ở việc chính sách allowlist/denylist được viết và test độc lập với mechanism, sau đó ta kiểm tra **đường interception** riêng.

### 9.3. Bài thực hành sửa rule

1. Đổi `module.equals("shared.api")` thành `module.startsWith("shared.")` và xem những module nào mới đủ điều kiện.
2. Bỏ điều kiện `app.generated.` khỏi exclude, dự đoán dòng `CONFIG` và `ADVICE` cho GeneratedService.
3. Đổi include thành chỉ `app.billing`, kiểm tra kết quả `app.orders` và `app.internal.x`.
4. Giữ nguyên rule nhưng gọi target `BillingService` trực tiếp, xác nhận chỉ scope đúng **chưa đủ** để advice chạy qua proxy.
5. Thêm một Service ném `IllegalArgumentException`, gọi qua proxy và chứng minh handler không vô tình nuốt exception hoặc bỏ qua phân loại lỗi.

## 10. Include/exclude ở mức type khác với include/exclude join point

Giả sử engine weave class `app.billing.InvoiceService` nhưng chỉ muốn quan sát method `issue`, không phải `preview`.

Có hai khả năng cấu hình kiến trúc:

**A. Weaving include cả type; pointcut lọc method.**

```text
eligible(type) = type under app.billing
pointcut(method) = execution of issue(...)
```

**B. Exclude type hoàn toàn rồi tìm cách include một method.**

Một số hệ thống **không cho phép** pointcut “cứu lại” một method trong class đã bị loại khỏi transformer; class không được biến đổi nghĩa là advice không có nơi để cài. Cách B có thể bất khả thi tùy engine.

Nguyên tắc: **chọn scope class đủ rộng để chứa những điểm cần can thiệp, rồi dùng pointcut hẹp để kiểm soát advice**. Nhưng đừng make scope class rộng đến mức transformer chạm vào quá nhiều dependencies không cần thiết.

### 10.1. Nếu muốn loại đúng một method

Nên ưu tiên **pointcut exclusion** nếu engine có khả năng chọn method chính xác, thay vì exclude cả class khiến những advice khác mất hook.

Ví dụ giả mã:

```text
pointcut:
  execution methods under app.billing
  AND NOT methodName("internalFlush")
```

Đây không phải cú pháp chung. Nếu `internalFlush` vẫn được một aspect khác chọn, nó có thể vẫn có advice của aspect khác, tùy cơ chế.

### 10.2. Nếu muốn loại một dependency hoàn toàn

Nếu mục tiêu là **không biến đổi bytecode của một thư viện** vì ổn định/tương thích, exclude ở weaving scope có thể phù hợp hơn việc yêu cầu từng pointcut phủ định package thư viện. Nhưng cần xác minh không có chức năng quan trọng phụ thuộc hook ở dependency đó.

## 11. Interface, implementation, inheritance và generated code

### 11.1. Nơi tên class được kiểm tra

Khi một class implement interface, một engine có thể match theo **implementation class**, theo interface, theo kiểu tĩnh ở call site hoặc theo runtime receiver, tùy loại join point và matcher. Rule include `app.api.*` không tự bảo đảm weave body của một implementation nằm ở `vendor.impl.*`.

Đối với JDK proxy, proxy triển khai interface và handler được gọi qua proxy; việc gắn rule vào interface không tương đương **biến đổi class implementation**. Đối với bytecode weaving, cần biết class nào thực sự được transformer xử lý.

### 11.2. Kế thừa và method override

Class con có thể kế thừa method từ superclass nằm ở module khác. Nếu transformer chỉ weave class con, method body thật có thể thuộc superclass; kết quả phụ thuộc engine và loại join point. Đừng dựa vào tên class nhận lời gọi mà bỏ qua **nơi code thực sự được định nghĩa**.

Nếu điểm cần theo dõi là execution của method kế thừa, hãy tạo test với superclass/interface ở package khác và xem nơi hook được cài.

### 11.3. Class lồng, anonymous, lambda, bridge và synthetic methods

Compiler có thể tạo class/member phụ không nhìn rõ như source. Trong Java:

- **Nested class** có tên binary khác với tên source thuận mắt.
- **Anonymous/local class** có các tên do compiler sinh.
- **Lambda** có thể được hiện thực bằng cơ chế runtime/compiler đặc thù.
- **Bridge method** có thể xuất hiện do generics/type erasure.
- Một số compiler/code generator tạo các method/synthetic artifacts.

Một wildcard chỉ khớp các class source do người viết tưởng tượng có thể bỏ qua hoặc bao gồm những class đã sinh không mong muốn. Khi mở rộng scope, test phải gồm **tên class thực hoặc bytecode thực trong artifact**, không chỉ tên package ở source tree.

### 11.4. Generated code là một quyết định có mục tiêu

Loại generated code thường giúp tránh noise, nhưng đôi khi thao tác quan trọng (serializer, RPC client, mapper) thực sự chạy trong code sinh. Nếu metric cần đo ở đó, phải xác định một boundary ổn định, có thể là API wrapper hoặc interface, thay vì vô tình exclude rồi cho rằng policy đã bao phủ.

## 12. Classloader, modules và dependencies

### 12.1. Cùng tên class, khác loader

Hai classloader khác nhau có thể định nghĩa các class cùng tên binary nhưng là các **kiểu runtime khác nhau**. Một policy chỉ dùng tên có thể có ý nghĩa khác với policy ràng buộc loader/module. Một transformer gắn với loader A không nhất thiết nhìn thấy class nạp qua loader B.

Khi debug “tên class khớp nhưng không weave”, nên kiểm tra **loader, module, artifact và thời điểm load**, không chỉ pointcut expression.

### 12.2. Runtime module boundaries

Module system có thể giới hạn truy cập kiểu, reflection hoặc instrumentation. Một engine có thể yêu cầu cấu hình mở module hoặc quyền đặc biệt; không được coi việc include module bằng pattern là đủ để vượt qua các ràng buộc runtime. Phải làm theo hợp đồng chính thức của công cụ, tránh tự tắt các cơ chế bảo vệ rộng hơn cần thiết.

### 12.3. Bên thứ ba và thư viện dùng chung

Một thư viện nằm trong nhiều ứng dụng có thể chạy với phiên bản/classloader khác. Nếu weave toàn thư viện, cần kiểm thử tương thích binary, hiệu năng, thứ tự transformer và ảnh hưởng tới mọi consumer. Có thể chọn can thiệp tại **application boundary** thay vì sửa bytecode của dependency nếu mục tiêu chỉ là đo lời gọi từ ứng dụng.

### 12.4. Điều gì xảy ra khi class đã được nạp?

Một số hook chỉ áp lúc class load. Nếu class đã load trước khi transformer được gắn, nó có thể không được weave, trừ khi cơ chế hỗ trợ retransformation và quy trình đó được chạy phù hợp. Không suy rằng đổi config sau startup sẽ tự sửa toàn bộ class đã load.

## 13. Weaving scope và multi-aspect interaction

Một application có nhiều aspect:

- Tracing.
- Metrics.
- Audit.
- Retry.
- Validation kỹ thuật.
- Resource cleanup.

Nếu exclude cả `app.internal.*` ở tầng weaving, **tất cả** aspect dựa trên cùng transformer có thể mất khả năng chọn join point ở vùng đó. Nhưng nếu chỉ thêm điều kiện `NOT internal` vào pointcut của **Metrics**, Tracing hoặc Audit vẫn có thể được áp dụng ở đó.

Vì vậy cần mô tả cấu hình dưới dạng ma trận:

| Thành phần | Eligible để weave? | Tracing? | Metrics? | Audit? |
| --- | --- | --- | --- | --- |
| `app.billing.InvoiceService` | Có | Có thể | Có thể | Có thể |
| `app.internal.metrics.Meter` | Theo chính sách | Có thể bị loại | Nên tránh tự instrument gây recursion | Tùy yêu cầu |
| `app.generated.Mapper` | Theo chính sách | Tùy chọn | Tùy chọn | Tùy yêu cầu |
| `vendor.PaymentClient` | Theo chính sách | Tùy hệ thống | Có thể quan sát từ wrapper bên ngoài | Tùy yêu cầu |

“Có thể” trong bảng không khẳng định advice đang chạy; nó nhắc rằng phải xét **eligible → pointcut → runtime occurrence** cho từng concern.

### 13.1. Nhiều công cụ weaving cùng một class

Trong một runtime, có thể có nhiều transformer hoặc công cụ code instrumentation. Thứ tự chúng chạy có thể ảnh hưởng bytecode đầu vào và khả năng tương thích. Nếu một class bị biến đổi nhiều lần, không thể mặc định mọi biến đổi đều độc lập hoặc commute.

Cần kiểm tra:
- Ownership của từng transformer.
- Thứ tự và tương thích phiên bản.
- Khả năng idempotency khi reweave.
- Cách phát hiện duplicate advice/hook.
- Quy trình rollback/inspect artifact.

Không tự điều chỉnh thứ tự agent trong production nếu chưa có test với artifact và phiên bản thực tế.

## 14. Khác biệt giữa “không weave” và “weave nhưng không chạy advice”

Đây là một bẫy chẩn đoán phổ biến.

**Tình huống A: class không được weave.**

```text
class: app.internal.Helper
scope exclude: match
transformer: không đưa class qua weaving
pointcut: có vẻ khớp method
runtime: không có hook tương ứng từ transformer đó
```

**Tình huống B: class được weave nhưng pointcut không khớp.**

```text
class: app.billing.InvoiceService
scope include: match
transformer: xử lý class
pointcut: chỉ method @Observed
method: preview() không có marker
runtime: không chạy advice trên preview()
```

**Tình huống C: có hook nhưng không có occurrence.**

```text
class eligible, pointcut matched, hook installed
nhánh code cần gọi method không được thực thi
=> không có advice invocation
```

**Tình huống D: proxy eligible nhưng bị bypass.**

```text
proxy được tạo
caller vẫn gọi target gốc
=> handler không chạy
```

Bốn nguyên nhân tạo **cùng triệu chứng “không thấy log advice”** nhưng cách khắc phục khác nhau. Không nên chỉ tăng độ rộng pointcut khi gốc lỗi là classloader hoặc artifact chưa weave.

## 15. Chiến lược xác minh weaving scope

### 15.1. Trước khi chạy: bảng mong đợi

Lập danh sách những type và kết quả mong đợi:

| Type / module | Include? | Exclude? | Kỳ vọng eligible |
| --- | --- | --- | --- |
| `app.orders.OrderService` | Có | Không | Có |
| `app.billing.InvoiceService` | Có | Không | Có |
| `app.internal.metrics.Meter` | Có nếu include `app.*` | Có | Không nếu deny-overrides |
| `app.generated.JsonMapper` | Có nếu include `app.*` | Có | Không nếu deny-overrides |
| `vendor.db.Client` | Không | Không | Không nếu default deny |
| `shared.api.Gateway` | Theo rule | Theo rule | Đọc từ rule cụ thể |

Đây là những **test input**, không phải tên class lấy từ dự án đang thực thi. Dùng tên class thật của ứng dụng khi viết kiểm thử production.

### 15.2. Trong build/load: diagnostic chứng minh transformation

Nhiều công cụ có tùy chọn chẩn đoán, dump/inspect mã đã weave, danh sách class đã xử lý hoặc thông báo các join point được nhận diện. Nếu công cụ thực sự hỗ trợ, có thể kiểm tra:

- File/class nào **đã được transformer nhìn thấy**?
- File/class nào **thực sự bị biến đổi**?
- Bao nhiêu shadow/join point đã được match?
- Những rule include/exclude nào tác động lên kết quả?
- Có lỗi parse, incompatible bytecode hoặc access error không?
- Artifact cuối cùng có chứa kết quả weaving không?

Phải phân biệt **“class được xét”** với **“class có thay đổi bytecode”**. Một class có thể được xem xét nhưng không có join point khớp nên output không thay đổi.

### 15.3. Trong runtime: positive và negative tests

Một bộ test cần cả hai vế:

1. **Positive:** type eligible, method pointcut khớp, caller đi qua cơ chế → advice xuất hiện đúng.
2. **Negative by scope:** type bị exclude → không có hook từ cơ chế đó.
3. **Negative by pointcut:** type eligible nhưng method không khớp → không có advice cụ thể.
4. **Negative by call path:** proxy eligible nhưng gọi target trực tiếp → không có advice của proxy.
5. **Conflict rule:** class match cả include/exclude → hành vi theo precedence đã chọn.
6. **Generated/inherited:** nested class, subclass, method bridge hoặc generated code → kết quả đúng hợp đồng.
7. **Multiple aspect:** một pointcut bị loại không làm mất những advice khác ngoài ý định.
8. **Rebuild/redeploy:** artifact dùng khi test trùng với artifact thực tế deploy.

Kiểm tra “advice có log trong happy path” không chứng minh exclude đúng. Ngược lại, kiểm tra “không có log” cũng không chứng minh class đã bị exclude, vì có thể method chưa hề chạy.

### 15.4. Kiểm thử thay đổi cấu hình

Khi sửa scope, so sánh **trước/sau**:

- Số class đủ điều kiện.
- Danh sách class mới được weave hoặc mới bị loại.
- Số join points được chọn theo từng aspect.
- Tần suất advice ở workload tương đương.
- Thời gian build/startup và runtime overhead.
- Lỗi classload/verification và xung đột với transformer khác.

Nếu phạm vi được quản lý như code, nên review thay đổi wildcard và các trường hợp `include + exclude` như thay đổi API/permission quan trọng.

## 16. Hiệu năng và kích thước tập weaving

Scope quá rộng có thể gây chi phí ở nhiều giai đoạn:

- **Scan/analysis:** duyệt nhiều class hoặc bytecode.
- **Transformation:** xử lý class thực sự cần biến đổi.
- **Build/rebuild:** cache/incremental compilation chịu ảnh hưởng cấu hình.
- **Class load/startup:** transformer có thể tăng thời gian khởi động.
- **Runtime:** những hook được cài có thể tạo overhead khi join point xảy ra.
- **Diagnostics:** nhiều điểm được instrument có thể tạo lượng log/metric lớn.

Nhưng đừng tự khẳng định “cứ exclude nhiều class thì runtime luôn nhanh hơn”. Một số engine tối ưu pointcut tĩnh tốt, có thể không chèn hook khi không khớp; nhiều chi phí nằm ở số **runtime occurrences**, không chỉ số class eligible. Phải đo bằng profile và benchmark trên workload thực.

### 16.1. Tập nhỏ không tự bảo đảm an toàn

Một method hot path chạy hàng triệu lần có thể tốn hơn rất nhiều so với hàng trăm class ít được gọi. Scope filter giúp giảm bề rộng biến đổi; **pointcut hẹp, sampling, log aggregation và hiệu năng advice** giúp giảm chi phí runtime.

### 16.2. Dữ liệu nhạy cảm

Weave một class chứa thao tác bảo mật/credentials rồi advice in toàn bộ arguments là rủi ro riêng tư. Exclude type có thể là một biện pháp phòng vệ nhưng không thay thế redaction và thiết kế telemetry tối thiểu, nhất là khi nhiều type chia sẻ cùng dữ liệu.

## 17. Những lỗi cấu hình thường gặp

**“Pointcut match thì class chắc chắn đã weave.”** Sai. Class có thể nằm ngoài eligible scope hoặc không được transformer nhìn thấy.

**“Include `app.*` nghĩa là include mọi class ở mọi package con.”** Không thể kết luận nếu chưa biết quy tắc wildcard của engine.

**“Exclude một package khỏi một pointcut nghĩa là engine không hề biến đổi class.”** Sai. Đó có thể chỉ là lọc advice, không phải lọc weaving.

**“Một class match cả include/exclude thì exclude luôn thắng.”** Chỉ đúng nếu chính sách engine đã được xác định hoặc lớp cấu hình của bạn hiện thực như vậy.

**“Loại trừ logger chắc chắn loại mọi recursion.”** Không luôn. Có thể còn những helper/callback khác bị pointcut chọn hoặc self-invocation theo cơ chế riêng.

**“Chỉ cấu hình include module ứng dụng nên dependencies sẽ không bị ảnh hưởng.”** Cần xem build classpath, transformer, classloader và cách engine xác định artifact; tên module trong source chưa đủ.

**“Cấu hình mới được deploy là class cũ đã được unweave.”** Không có bảo đảm chung. Có thể cần rebuild/restart/retransform theo khả năng công cụ.

**“Không có log advice chứng minh class bị exclude đúng.”** Sai. Method có thể chưa xảy ra hoặc pointcut không khớp.

**“Thấy aspect được load nghĩa là target đã weave.”** Sai. Đó là hai trạng thái khác nhau.

**“Generated code nên luôn bị loại.”** Không phải nguyên tắc tuyệt đối; đôi khi điểm tích hợp đúng nằm trong generated wrapper hoặc serializer.

**“Weaving scope thay được kiểm tra quyền ở domain boundary.”** Sai khi có đường bypass hoặc chính sách không bao trùm tất cả truy cập quan trọng.

**“Có thể dùng config thật của một công cụ với bất cứ AOP engine nào.”** Không. Những ví dụ include/exclude trong bài là kiến trúc và giả mã, cú pháp cụ thể phải theo công cụ.

## 18. Bài tập và đáp án

### Bài 1 — Rule precedence

Có:

```text
include app.*
exclude app.internal.*
include app.internal.audit.*
```

Nếu **chính sách được công bố** là `included AND NOT excluded`, class `app.internal.audit.Writer` có eligible không?

**Đáp án:** Không. Nó khớp include nhưng cũng khớp exclude; exclude thắng theo policy được định nghĩa. Nếu engine dùng last-match wins thì câu trả lời có thể khác, nên phải xác minh contract.

### Bài 2 — Class eligible nhưng advice không có log

`app.billing.InvoiceService` nằm trong include. Pointcut chỉ chọn method `@Observed`; method `preview` không có marker và được gọi 10 lần. Có thể kết luận weaving sai không?

**Đáp án:** Không. Type eligible không có nghĩa tất cả method được advice chọn. Cần inspect pointcut/matcher và kiểm thử một method có marker.

### Bài 3 — Hai loại exclude

Bạn muốn metrics không chạy trên `MetricsWriter` nhưng audit vẫn chạy. Nên exclude cả class ở weaving scope hay loại riêng pointcut metrics?

**Đáp án:** Thường nên xem xét **loại khỏi pointcut metrics** để không vô tình mất audit; tất nhiên phải xét recursion, khả năng engine và chính sách tách instrumentation thực tế.

### Bài 4 — Direct target call

Một interface proxy được tạo thành công, nhưng caller vẫn giữ tham chiếu gốc. Rule eligible=true. Advice có nhất thiết chạy?

**Đáp án:** Không. Handler proxy chỉ quan sát những lời gọi qua proxy. Eligibility và đường runtime là hai tầng khác nhau.

### Bài 5 — Load-time scope

Class đã được loader B nạp trước khi transformer gắn với loader A. Tên class khớp include. Có thể khẳng định bytecode đã weave không?

**Đáp án:** Không. Phải kiểm tra loader/transformer, thời điểm load và cơ chế retransformation. Include theo tên không đủ.

### Bài 6 — Generated code

Compiler sinh nested class với binary name khác dự đoán từ source. Pattern exclude chỉ dựa vào tên class source. Rủi ro là gì?

**Đáp án:** Có thể chưa loại được class thực tế, hoặc loại nhầm phần khác; cần kiểm thử tên binary/resource và artifact output.

### Bài 7 — Hai aspect

Tracing và audit cùng cần `app.orders.OrderService`. Một cấu hình exclude ở weaving scope vô tình loại class này. Điều gì xảy ra?

**Đáp án:** Nếu cả hai cần cùng hook weaving trên class đó, chúng có thể mất tác động. Phải phân biệt loại một advice với loại cả target khỏi eligible scope.

### Bài 8 — Performance

Include 20 class nhưng một method được gọi một triệu lần/giây. Include 500 class khác rất ít chạy. Từ số class alone có thể khẳng định cấu hình nào nhanh hơn?

**Đáp án:** Không. Cần xem chi phí scan/build/startup và tần suất runtime/advice overhead thực tế.

### Bài 9 — Thay đổi scope khi runtime đang hoạt động

Chỉnh exclude pattern rồi hot-reload config. Những class đã weave có tự quay về code cũ không?

**Đáp án:** Không thể mặc định. Phải tra hợp đồng của cơ chế transform/retransform, classloader và rollout; có thể cần rebuild hoặc restart.

## 19. Checklist triển khai một weaving policy đáng tin

1. **Nêu rõ mục tiêu:** Đang chọn type để weaving hay join point cho một advice cụ thể?
2. **Xác định join-point model:** Method execution/call, field/constructor hay interception theo proxy?
3. **Khai báo include:** Các namespace/module/artifact cần được xem xét; ưu tiên allowlist có chủ đích.
4. **Khai báo exclude:** Instrumentation internals, generated classes hoặc dependencies với lý do rõ ràng.
5. **Quy định default và precedence:** Match cả hai rule thì kết quả gì? Không match include thì sao?
6. **Kiểm tra wildcard:** Regex, package delimiter, nested/binary class name, case sensitivity.
7. **Xác định thời điểm:** Build, load hay runtime, và ảnh hưởng của cache/incremental/redeploy.
8. **Xác định loader/module:** Transformer thật sự thấy những class nào?
9. **Phân biệt aspects và targets:** Có loại nhầm một class cần cho aspect khác không?
10. **Chứng minh bằng artifact:** Có inspection/diagnostics phù hợp chứng minh class nào đã biến đổi?
11. **Chứng minh bằng runtime:** Có positive/negative test cho pointcut và call path?
12. **Bảo vệ correctness:** Thay đổi exclude không tạo bypass cho policy quan trọng.
13. **Kiểm soát hiệu năng:** Giới hạn hot path, dữ liệu log/metric và class processing.
14. **Quản lý thay đổi:** Review diff của eligible set và test khi refactor module/package.
15. **Rollback:** Có cơ chế khôi phục artifact hoặc cấu hình trước nếu xảy ra xung đột weaving?

## Kết luận

**Weaving scope** định nghĩa **những đơn vị mã có khả năng được công cụ xem xét và biến đổi**; **pointcut** định nghĩa **những join point nào được chọn**; còn **runtime call path** quyết định **lượt thực thi nào thật sự đi qua hook**. Ba tầng này liên quan nhưng không thay thế nhau.

Để cấu hình phạm vi được dệt và loại trừ an toàn, hãy chọn include có chủ đích, quy định exclude và precedence rõ, chú ý classloader/module/build artifact, tách loại trừ ở tầng weaving khỏi loại trừ của từng advice, rồi chứng minh bằng test **cả điểm được chọn lẫn điểm bị loại**. Đừng chỉ dựa vào một biểu thức pointcut nhìn hợp lý hoặc một dòng log thành công: chất lượng của kiến trúc weaving nằm ở **độ phủ có thể kiểm chứng, biên giới rõ ràng, sự tương thích của artifact và khả năng thay đổi mà không tạo tác động ngoài dự kiến**.
