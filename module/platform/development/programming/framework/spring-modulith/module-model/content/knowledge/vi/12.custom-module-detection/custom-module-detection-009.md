# Đánh giá chi phí bảo trì của detection tùy biến

Trong Spring Modulith, chiến lược phát hiện module quyết định package nào được xem là ranh giới của một application module. Một chiến lược tùy biến có thể giúp mô hình module khớp với cấu trúc package hiện có, nhưng nó cũng tạo thêm một quy tắc kiến trúc mà nhóm phải hiểu, kiểm thử và duy trì qua các lần thay đổi mã nguồn.

Vì vậy, câu hỏi quan trọng không chỉ là *có thể viết custom detection hay không*, mà là *lợi ích của nó có đủ lớn để bù chi phí trong suốt vòng đời ứng dụng hay không*. Bài học này đưa ra cách đánh giá có căn cứ, cách so sánh các lựa chọn và cách giới hạn chi phí sau khi đã chọn chiến lược tùy biến.

## Mục tiêu

Sau bài học, bạn có thể:

- Nhận diện những loại chi phí phát sinh khi tự triển khai `ApplicationModuleDetectionStrategy`.
- So sánh detection mặc định, detection dựa trên annotation và detection tùy biến.
- Xác định trường hợp custom detection đem lại giá trị đủ lớn.
- Thiết kế kiểm thử để phát hiện sớm thay đổi cấu trúc package làm sai kết quả discovery.
- Lập kế hoạch giảm chi phí bảo trì khi package, module hoặc phiên bản Spring Modulith thay đổi.

## Custom detection nằm ở đâu trong mô hình module?

`ApplicationModules` phân tích package của ứng dụng để tạo mô hình các application module. Theo mặc định, Spring Modulith xem các package con trực tiếp của package chứa lớp Spring Boot application là module. Ví dụ, với package gốc `com.acme`, các package `com.acme.orders` và `com.acme.inventory` có thể được phát hiện thành hai module.

Khi muốn đánh dấu module một cách tường minh, bạn có thể dùng `@ApplicationModule` và chiến lược `explicitly-annotated`:

```properties
spring.modulith.detection-strategy=explicitly-annotated
```

Nếu hai cách trên không diễn tả được cấu trúc package, Spring Modulith cung cấp SPI `ApplicationModuleDetectionStrategy`. Hợp đồng cốt lõi để chọn module nhận package gốc dưới dạng `JavaPackage` và trả về `Stream<JavaPackage>` chứa các package gốc cần xem là module:

```java
Stream<JavaPackage> getModuleBasePackages(JavaPackage rootPackage);
```

Ở các phiên bản mới, SPI còn có điểm mở rộng riêng để tùy biến việc phát hiện `NamedInterfaces`. Chỉ nên dùng phần mở rộng đó khi nhóm thật sự cần thay đổi quy tắc nhận diện API công khai của module; việc chọn package gốc và việc chọn named interface là hai quyết định kiến trúc khác nhau.

Với các phiên bản Spring Modulith hiện hành, có thể cấu hình tên lớp strategy bằng property:

```properties
spring.modulith.detection-strategy=com.acme.architecture.BoundedContextDetectionStrategy
```

Hãy kiểm tra tài liệu đúng phiên bản đang sử dụng trước khi triển khai. Cơ chế đăng ký đã thay đổi giữa các phiên bản; chẳng hạn, tài liệu Spring Modulith 1.1 mô tả việc đăng ký strategy qua `META-INF/spring.factories`, trong khi tài liệu hiện hành mô tả property `spring.modulith.detection-strategy`.

Phần detection được bàn trong bài này quyết định package nào trở thành module gốc. Sau bước đó, Spring Modulith dùng mô hình module để kiểm tra quan hệ phụ thuộc, named interface và các quy tắc kiến trúc liên quan. Vì vậy, một strategy phát hiện sai có thể làm toàn bộ kết quả kiểm tra kiến trúc sai theo.

## Những khoản chi phí phải tính

Không nên đánh giá custom detection chỉ bằng số dòng Java cần viết. Chi phí thật xuất hiện trong mỗi lần nhóm thay đổi cấu trúc ứng dụng hoặc nâng cấp công cụ.

### Chi phí triển khai và độ phức tạp

Strategy phải diễn đạt được một quy tắc ổn định để tìm module. Quy tắc càng phụ thuộc vào nhiều điều kiện, chi phí đọc hiểu và sửa đổi càng cao. Ví dụ, một strategy chọn module theo một package trung gian cố định thường dễ hiểu hơn strategy kết hợp tên package, annotation nội bộ, cấu hình môi trường và ngoại lệ riêng cho từng nhóm.

Hãy tự hỏi:

- Quy tắc có thể mô tả trong một hoặc hai câu không?
- Một thành viên mới có thể dự đoán package nào sẽ trở thành module không?
- Kết quả có phụ thuộc vào thứ tự quét, môi trường chạy hoặc trạng thái bên ngoài không?
- Khi thêm module, nhóm chỉ cần tuân thủ một quy ước hay phải sửa nhiều nhánh điều kiện?

Nếu không thể giải thích quy tắc ngắn gọn, đó là dấu hiệu strategy đang chứa quá nhiều kiến thức về cấu trúc ứng dụng.

### Chi phí kiểm thử

Một strategy có thể biên dịch thành công nhưng vẫn phát hiện thiếu module, thừa module hoặc chọn nhầm package kỹ thuật làm module nghiệp vụ. Do đó, nhóm cần kiểm thử cả kết quả discovery và các quy tắc phụ thuộc được xây dựng trên kết quả đó.

Các trường hợp cần kiểm tra gồm:

- Mỗi module dự kiến đều được phát hiện.
- Package dùng cho cấu hình, adapter hoặc tiện ích chung không vô tình trở thành module.
- Package con nằm sâu hơn một cấp được xử lý đúng theo quy ước.
- Thêm, đổi tên hoặc di chuyển package không âm thầm làm thay đổi tập module.
- Strategy xử lý rõ ràng khi không tìm thấy module hoặc khi có package trùng quy tắc.

Lệnh kiểm tra kiến trúc cơ bản vẫn hữu ích:

```java
class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(Application.class).verify();
    }
}
```

`verify()` giúp kiểm tra các quy tắc kiến trúc trên mô hình module đã được tạo. Tuy nhiên, chỉ gọi `verify()` chưa đủ chứng minh tập module được phát hiện đúng với ý định nghiệp vụ. Hãy bổ sung kiểm tra rõ ràng cho danh sách module mong đợi, hoặc kiểm tra tài liệu mô hình được sinh ra trong quy trình CI. Khi đó, việc thêm một package mới không thể âm thầm thay đổi ranh giới module mà không bị phát hiện.

### Chi phí thay đổi cấu trúc package

Package là một phần của quy ước discovery. Khi nhóm đổi tên package, chuyển module sang namespace khác hoặc tách một bounded context, strategy có thể cần thay đổi cùng lúc. Một quy tắc dựa trên tên như `*.domain.*` có thể vô tình chọn package con mới trong tương lai; một allowlist cố định lại yêu cầu cập nhật mỗi khi có module mới.

Hãy ghi rõ các giả định mà strategy dựa vào, chẳng hạn:

- Module luôn nằm dưới package `com.acme.contexts`.
- Mỗi bounded context có đúng một package gốc.
- Package `shared` không được xem là module nghiệp vụ.
- Tên package là định danh kỹ thuật, không phải tên hiển thị của module.

Các giả định này nên được xem như hợp đồng kiến trúc. Khi thay đổi cấu trúc package, người thực hiện cần cập nhật strategy, kiểm thử và tài liệu trong cùng một thay đổi.

### Chi phí nâng cấp và tương thích

Custom strategy phụ thuộc vào SPI của Spring Modulith. Khi nâng cấp Spring Modulith, nhóm cần kiểm tra thay đổi API, cách cấu hình strategy và hành vi discovery. Nếu strategy chỉ dùng API công khai và có kiểm thử tập module mong đợi, việc nâng cấp thường dễ đánh giá hơn.

Không nên dựa vào lớp nội bộ hoặc cách quét package không được tài liệu hóa. Nếu phiên bản mới thay đổi cơ chế đăng ký, hãy cập nhật cấu hình theo tài liệu phiên bản đó và chạy lại kiểm thử discovery trong CI.

### Chi phí vận hành và truyền đạt kiến thức

Người phát triển cần biết strategy đang được kích hoạt ở đâu, package nào được chọn và vì sao. Nếu cấu hình chỉ xuất hiện trong một file ít được chú ý, thành viên mới có thể hiểu nhầm rằng quy ước mặc định của Spring Modulith vẫn đang được dùng.

Đặt cấu hình ở vị trí dễ tìm, đặt tên lớp theo mục đích nghiệp vụ và ghi một ví dụ package hợp lệ trong tài liệu kiến trúc. Khi strategy có nhiều ngoại lệ, hãy cân nhắc liệu ngoại lệ đó có đang che giấu một cấu trúc package cần được đơn giản hóa hay không.

## So sánh các lựa chọn

| Lựa chọn | Chi phí duy trì | Khi phù hợp | Điểm cần chú ý |
|---|---|---|---|
| Detection mặc định (`direct-subpackages`) | Thấp | Module là package con trực tiếp của package ứng dụng | Cần giữ cấu trúc package nhất quán |
| Detection tường minh (`explicitly-annotated`) | Thấp đến trung bình | Muốn đánh dấu rõ package module bằng annotation | Cần duy trì annotation trên mọi module |
| Custom `ApplicationModuleDetectionStrategy` | Trung bình đến cao | Có quy ước package ổn định mà hai lựa chọn trên không biểu diễn được | Phải sở hữu logic, kiểm thử, tài liệu và tương thích phiên bản |

Chi phí còn phụ thuộc số lượng quy tắc và tốc độ thay đổi cấu trúc ứng dụng. Một custom strategy rất ngắn, thuần túy và ổn định có thể rẻ hơn việc buộc một codebase lớn phải di chuyển package. Ngược lại, strategy với nhiều ngoại lệ có thể đắt hơn việc chuẩn hóa lại package một lần.

## Cách ước lượng tổng chi phí

Khi đưa ra quyết định, hãy ước lượng chi phí trong một khoảng thời gian đủ dài, chẳng hạn một năm hoặc một chu kỳ phát hành lớn. Có thể dùng mô hình định tính sau:

\[
C_{total} = C_{implementation} + C_{tests} + C_{documentation} + C_{change} + C_{upgrade} + C_{debugging}
\]

Trong đó:

- `C_implementation`: thời gian thiết kế, viết và review strategy.
- `C_tests`: thời gian tạo và cập nhật kiểm thử discovery.
- `C_documentation`: thời gian giải thích quy tắc cho nhóm.
- `C_change`: thời gian cập nhật strategy khi package hoặc module thay đổi.
- `C_upgrade`: thời gian xác minh tương thích khi nâng cấp Spring Modulith.
- `C_debugging`: thời gian tìm nguyên nhân khi một module bị thiếu hoặc bị phát hiện nhầm.

So sánh tổng này với chi phí của phương án khác, ví dụ chuẩn hóa package hoặc bổ sung `@ApplicationModule`. Cũng cần tính đến chi phí chuyển đổi ban đầu và rủi ro của từng phương án. Không cần đưa ra con số chính xác tuyệt đối; mục đích là làm lộ ra các khoản chi phí thường bị bỏ quên.

Một bảng đánh giá ngắn có thể giúp nhóm thống nhất quyết định:

| Tiêu chí | Câu hỏi đánh giá | Dấu hiệu tích cực |
|---|---|---|
| Giá trị | Custom detection giải quyết trở ngại cụ thể nào? | Có vấn đề cấu trúc rõ ràng mà cách mặc định không xử lý được |
| Độ ổn định | Quy ước package có thường xuyên thay đổi không? | Quy ước ít thay đổi và được nhóm thống nhất |
| Độ đơn giản | Logic có dễ đọc và dự đoán không? | Một quy tắc ngắn, không phụ thuộc môi trường |
| Khả năng kiểm thử | Có thể xác định tập module mong đợi không? | Có kiểm tra tự động cho module thiếu và module thừa |
| Khả năng sở hữu | Có người hiểu và chịu trách nhiệm với quy tắc không? | Quy tắc có chủ sở hữu và tài liệu rõ ràng |
| Tương thích | Có thể kiểm tra sau mỗi lần nâng cấp không? | Dùng API công khai và có kiểm thử chạy trong CI |

## Ví dụ: module nằm dưới package bounded context

Giả sử ứng dụng có cấu trúc:

```text
com.acme
└── contexts
    ├── orders
    │   ├── api
    │   └── internal
    ├── inventory
    │   ├── api
    │   └── internal
    └── billing
        ├── api
        └── internal
```

Package ứng dụng là `com.acme`. Detection mặc định nhìn các package con trực tiếp của nó, nên có thể coi `contexts` là một module. Nhưng ý định kiến trúc của nhóm là có ba module `orders`, `inventory` và `billing`.

Trước khi viết custom strategy, hãy đánh giá theo thứ tự:

1. **Có thể chuẩn hóa package không?** Nếu chuyển ba module thành `com.acme.orders`, `com.acme.inventory` và `com.acme.billing` không gây ảnh hưởng lớn, detection mặc định thường là lựa chọn dễ duy trì nhất.
2. **Có thể dùng annotation không?** Nếu nhóm muốn giữ cấu trúc `contexts`, hãy xem xét đánh dấu trực tiếp các package gốc module bằng `@ApplicationModule` và dùng `explicitly-annotated`.
3. **Có quy tắc chung đủ ổn định không?** Nếu số lượng bounded context thay đổi thường xuyên nhưng tất cả luôn nằm trực tiếp dưới `com.acme.contexts`, custom strategy có thể chọn các package con của namespace này. Quy tắc cần loại trừ package kỹ thuật và phải có kiểm thử cho cả module mới lẫn package không phải module.

Ở lựa chọn thứ ba, logic discovery nên chỉ làm một việc: chuyển quy ước package đã thống nhất thành tập `JavaPackage` đại diện cho module. Tránh để strategy đọc cấu hình nghiệp vụ, khởi tạo Spring context hoặc gọi dịch vụ bên ngoài. Discovery cần có kết quả xác định để cùng một mã nguồn tạo ra cùng một mô hình module trong máy phát triển và CI.

Giả sử trong tương lai nhóm thêm `com.acme.contexts.reporting`. Nếu đây là bounded context mới, kiểm thử cần xác nhận nó được phát hiện. Nếu nhóm thêm `com.acme.contexts.shared-kernel` chỉ để gom mã dùng chung, kiểm thử cần xác nhận package đó không bị chọn nhầm thành module nếu kiến trúc không chủ định như vậy. Hai trường hợp này làm rõ giá trị của kiểm thử tập module mong đợi.

Nếu yêu cầu thực tế là đóng góp module từ nhiều package gốc độc lập, hãy xem xét `ApplicationModuleSourceFactory` (được Spring Modulith hỗ trợ từ phiên bản 1.3) thay vì làm một strategy duy nhất phải biết mọi namespace. Chọn extension point theo đúng vấn đề cần giải quyết sẽ giúp giảm số quy tắc phải duy trì.

## Các cách giới hạn chi phí sau khi chọn custom detection

**Giữ strategy thuần và xác định.** Chỉ dựa vào `JavaPackage` đầu vào và quy tắc package đã công bố. Không dùng trạng thái môi trường, thời điểm chạy, truy vấn mạng hoặc dữ liệu thay đổi bên ngoài.

**Ưu tiên quy tắc tổng quát, hạn chế ngoại lệ.** Một quy tắc như “các package con trực tiếp của `contexts` là module” dễ truyền đạt hơn danh sách nhiều điều kiện riêng cho từng module. Nếu cần quá nhiều ngoại lệ, hãy xem lại cấu trúc package hoặc ranh giới module.

**Kiểm thử cả trường hợp dương và âm.** Kiểm tra module phải được phát hiện, package không phải module phải bị loại trừ, và package mới phải tuân thủ đúng quy ước. Chỉ kiểm tra rằng `verify()` không ném lỗi là chưa đủ để xác nhận tập module chính xác.

**Đưa cấu hình vào cùng quy trình kiểm thử.** Kiểm thử cần chạy với đúng cấu hình strategy được dùng trong dự án. Nếu production sử dụng các thành phần runtime của Spring Modulith dựa trên mô hình module, hãy xác nhận dependency và cấu hình runtime cần thiết theo tài liệu phiên bản đang dùng.

**Ghi lại hợp đồng kiến trúc.** Tài liệu nên có package gốc, quy tắc chọn module, package bị loại trừ, ví dụ hợp lệ và cách chạy kiểm thử. Cập nhật tài liệu cùng commit thay đổi strategy hoặc cấu trúc package.

**Đánh giá lại định kỳ.** Khi cấu trúc package đã được chuẩn hóa hoặc Spring Modulith cung cấp lựa chọn mặc định phù hợp hơn, hãy cân nhắc xóa strategy tùy biến. Mã tùy biến chỉ có giá trị khi nó tiếp tục giải quyết một nhu cầu thực tế.

## Quy trình ra quyết định

Có thể áp dụng quy trình sau trong review kiến trúc:

1. Mô tả chính xác module nào cần được phát hiện và vì sao cấu trúc hiện tại không phù hợp.
2. Thử diễn đạt cùng kết quả bằng detection mặc định hoặc `explicitly-annotated`.
3. Nếu vẫn cần custom detection, viết quy tắc discovery thành một câu và liệt kê các package phải được chọn hoặc loại trừ.
4. Ước lượng chi phí triển khai, kiểm thử, tài liệu, thay đổi và nâng cấp.
5. Tạo kiểm thử cho tập module mong đợi trước khi đưa strategy vào sử dụng rộng rãi.
6. Ghi rõ chủ sở hữu và điều kiện cần đánh giá lại quyết định.

## Bài tập tự đánh giá

Một nhóm có 18 bounded context nằm dưới `com.example.business`. Các module được tạo và tách tương đối thường xuyên. Trong namespace này còn có `shared`, `configuration` và `support`, là các package kỹ thuật không được xem là module nghiệp vụ. Nhóm đề xuất custom strategy chọn tất cả package con trực tiếp, sau đó loại trừ ba tên package kỹ thuật.

Hãy trả lời:

1. Quy tắc này có dễ duy trì khi một bounded context mới được thêm không?
2. Điều gì xảy ra nếu một nhóm tạo package kỹ thuật mới nhưng quên cập nhật danh sách loại trừ?
3. Bạn sẽ viết những kiểm thử nào để phát hiện module thừa và module bị thiếu?
4. Trong trường hợp này, dùng annotation tường minh có lợi ích gì và tạo thêm công việc nào?
5. Điều kiện nào khiến nhóm nên chuẩn hóa package hoặc thay đổi chiến lược discovery?

Một câu trả lời tốt cần chỉ ra cả lợi ích lẫn chi phí. Việc có 18 bounded context và thường xuyên thêm module có thể khiến quy tắc tự động trở nên hấp dẫn. Tuy nhiên, danh sách loại trừ là một phần của hợp đồng kiến trúc: nếu không có kiểm thử cho package kỹ thuật mới, strategy có thể âm thầm biến package đó thành module. Nhóm cần so sánh rủi ro này với chi phí duy trì annotation trên từng bounded context.

## Kết luận

Custom detection đáng dùng khi nó diễn đạt một quy ước package ổn định mà detection mặc định và detection dựa trên annotation không thể mô tả hợp lý. Chi phí của nó gồm logic discovery, kiểm thử tập module, tài liệu, xử lý thay đổi package và tương thích khi nâng cấp Spring Modulith. Giữ strategy nhỏ, xác định, có kiểm thử cả trường hợp được chọn lẫn bị loại trừ sẽ giúp nhóm kiểm soát các chi phí đó.

## Tài liệu tham khảo

- [Spring Modulith Reference — Fundamentals, Customizing Module Detection](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith API — `ApplicationModuleDetectionStrategy`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDetectionStrategy.html)
- [Spring Modulith API — `ApplicationModuleSourceFactory`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleSourceFactory.html)
