# Đọc quy ước phiên bản ngữ nghĩa và giới hạn của cam kết tương thích

Trong dự án Java, phiên bản xuất hiện ở nhiều nơi: thư viện, plugin Gradle, plugin Maven, ứng dụng, artifact phát hành và cả API mà các module khác sử dụng. Một số version chỉ là nhãn để phân biệt bản build; một số khác còn thể hiện cam kết về mức độ tương thích khi nâng cấp.

Semantic Versioning (SemVer) là quy ước phổ biến để diễn đạt cam kết đó bằng ba thành phần `MAJOR.MINOR.PATCH`. Khi hiểu đúng quy ước, người dùng có thể ước lượng mức độ rủi ro khi nâng version và nhà phát triển có nguyên tắc rõ hơn khi phát hành. Tuy nhiên, SemVer chỉ có ý nghĩa trong phạm vi API công khai và chính sách tương thích mà dự án thực sự cam kết. Một chuỗi version đúng định dạng không tự chứng minh rằng hai bản phát hành tương thích với nhau.

## 1. Semantic Versioning là gì?

Semantic Versioning 2.0.0 (thường viết tắt SemVer) là quy ước đánh số phiên bản cho phần mềm. Một phiên bản ổn định có dạng:

```text
MAJOR.MINOR.PATCH
```

Ví dụ:

```text
2.4.7
```

Trong đó:

- **MAJOR** (`2`): tăng khi có thay đổi không tương thích với API công khai đã cam kết.
- **MINOR** (`4`): tăng khi bổ sung chức năng tương thích ngược với API công khai hiện có.
- **PATCH** (`7`): tăng khi sửa lỗi tương thích ngược, không làm thay đổi hợp đồng API theo cách phá vỡ người dùng.

Với một thư viện Java, có thể hình dung:

| Thay đổi | Ví dụ | Thành phần version thường tăng |
|---|---|---|
| Sửa lỗi mà không phá hợp đồng API | Sửa trường hợp tính toán sai nhưng giữ nguyên chữ ký và hành vi được tài liệu hóa. | PATCH |
| Bổ sung API hoặc tính năng tương thích ngược | Thêm một overload mới hoặc thêm một lớp công khai mới mà không làm hỏng cách sử dụng cũ. | MINOR |
| Thay đổi không tương thích | Xóa phương thức công khai, đổi kiểu tham số hoặc thay đổi hợp đồng khiến mã khách hàng hiện tại không còn hoạt động đúng. | MAJOR |

SemVer không chỉ là cách viết ba con số. Nó là lời hứa về cách phần mềm sẽ thay đổi giữa các lần phát hành. Lời hứa chỉ đáng tin khi dự án xác định rõ API công khai, phạm vi tương thích và cách kiểm tra các thay đổi.

## 2. API công khai là cơ sở của lời hứa tương thích

SemVer dựa trên khái niệm *public API*: những giao diện mà người dùng được kỳ vọng sử dụng và dự án cam kết duy trì theo chính sách của mình.

Trong thư viện Java, public API thường bao gồm:

- Các package, class, interface, enum và annotation được công bố để người dùng sử dụng.
- Constructor, method, field và kiểu generic công khai.
- Hợp đồng hành vi được tài liệu hóa, chẳng hạn giá trị trả về, exception, thứ tự xử lý và quy tắc null.
- Các file cấu hình, extension point, annotation hoặc SPI mà thư viện tuyên bố hỗ trợ.
- Với Gradle plugin, plugin ID, extension DSL, task và thuộc tính được công bố như giao diện cấu hình.

Không phải mọi lớp có modifier `public` trong mã nguồn đều mặc nhiên thuộc public API được hỗ trợ. Một số dự án có package nội bộ, lớp implementation hoặc API đánh dấu incubating/experimental. Dự án cần công bố ranh giới này bằng tài liệu, annotation, module export, quy ước package hoặc chính sách support rõ ràng.

Ngược lại, một hợp đồng có thể tồn tại ngoài chữ ký Java. Ví dụ, người dùng dựa vào thứ tự phần tử trong output, format file cấu hình, tên task Gradle hoặc cách một plugin tạo artifact. Nếu dự án đã công bố và hỗ trợ các hành vi đó, thay đổi chúng cũng có thể là breaking change dù compiler vẫn biên dịch thành công.

### 2.1. Ví dụ về API công khai

Giả sử thư viện cung cấp:

```java
package com.example.billing;

public class InvoiceCalculator {
    public long total(long unitPrice, int quantity) {
        return unitPrice * quantity;
    }
}
```

Người dùng có thể gọi:

```java
InvoiceCalculator calculator = new InvoiceCalculator();
long amount = calculator.total(1200L, 3);
```

Nếu thư viện phát hành bản mới và xóa method `total(long, int)`, mã khách hàng đang gọi method đó không còn biên dịch. Đây là thay đổi không tương thích ở source API và thường cần tăng MAJOR theo SemVer nếu method thuộc public API đã cam kết.

Nếu thư viện bổ sung overload:

```java
public long total(long unitPrice, int quantity, long discount) {
    return unitPrice * quantity - discount;
}
```

và giữ nguyên method cũ cùng hợp đồng, thay đổi này thường là bổ sung tương thích ngược, phù hợp với MINOR.

## 3. Cách đọc MAJOR, MINOR và PATCH

### 3.1. PATCH: sửa lỗi tương thích ngược

Ví dụ:

```text
2.4.6 -> 2.4.7
```

Một bản patch thường sửa lỗi mà không yêu cầu người dùng thay đổi cách gọi API công khai. Ví dụ thư viện sửa lỗi làm tròn số trong một trường hợp biên nhưng vẫn giữ nguyên chữ ký method và hợp đồng đầu vào/đầu ra được tài liệu hóa.

Patch không có nghĩa là thay đổi nhỏ về số dòng code. Một sửa lỗi có thể thay đổi nhiều file nội bộ, cập nhật dependency hoặc tối ưu thuật toán. Điều quan trọng là bản phát hành vẫn tương thích với những gì đã cam kết.

Có một giới hạn cần lưu ý: nếu người dùng phụ thuộc vào hành vi sai do bug tạo ra, sửa bug có thể làm chương trình của họ thay đổi kết quả. SemVer thường coi hành vi ngoài hợp đồng hoặc lỗi đã được xác định là bug không phải một phần của public API. Nhưng nếu hành vi đó đã được tài liệu hóa, được hỗ trợ hoặc được nhiều người dùng dựa vào như một hợp đồng thực tế, việc sửa có thể gây tác động lớn. Chính sách versioning không thể thay thế việc đánh giá ảnh hưởng.

### 3.2. MINOR: bổ sung chức năng tương thích ngược

Ví dụ:

```text
2.4.7 -> 2.5.0
```

Khi tăng MINOR, PATCH được đặt về `0`. Bản minor có thể bổ sung API, tính năng hoặc khả năng mới mà vẫn giữ cách sử dụng cũ.

Ví dụ:

- Thêm method mới mà không xóa hoặc đổi method cũ.
- Thêm một implementation mới của interface theo cách người dùng hiện tại vẫn sử dụng được.
- Thêm một cấu hình tùy chọn có default giữ nguyên hành vi cũ.
- Thêm task mới cho Gradle plugin mà không thay đổi task hoặc extension đã công bố.

Tuy nhiên, thêm API vẫn có thể tạo xung đột source compatibility trong một số trường hợp Java. Ví dụ, thêm một overload có thể khiến lời gọi vốn biên dịch trước đây trở nên mơ hồ hoặc chọn overload khác. Vì vậy, “chỉ thêm API” không tự động bảo đảm mọi thay đổi đều an toàn; cần kiểm tra tương tác với mã khách hàng.

### 3.3. MAJOR: thay đổi không tương thích

Ví dụ:

```text
2.5.0 -> 3.0.0
```

Khi tăng MAJOR, MINOR và PATCH được đặt về `0`. Đây là tín hiệu cho người dùng rằng bản mới có thể yêu cầu điều chỉnh mã, cấu hình hoặc quy trình tích hợp.

Ví dụ breaking change:

- Xóa hoặc đổi tên class, method, constructor hay field công khai.
- Đổi kiểu tham số hoặc kiểu trả về khiến client không biên dịch hoặc thay đổi cách dispatch.
- Đổi format file cấu hình mà không hỗ trợ cấu hình cũ.
- Thay đổi hợp đồng exception, nullability hoặc semantics đã được tài liệu hóa.
- Đổi plugin ID, tên extension hoặc thuộc tính DSL mà người dùng đang cấu hình.
- Nâng yêu cầu runtime lên một phiên bản Java mới hơn khiến ứng dụng dùng runtime cũ không thể chạy.

Tăng MAJOR không có nghĩa bản mới chắc chắn không tương thích với mọi người dùng. Nó có nghĩa người phát hành không còn cam kết duy trì toàn bộ tương thích với public API của major trước. Một số người dùng có thể nâng cấp mà không cần sửa code, nhưng vẫn phải đọc release notes và kiểm thử.

## 4. Số 0 và giai đoạn phát triển trước 1.0.0

SemVer dành ý nghĩa đặc biệt cho version `0.y.z`:

```text
0.1.0
0.2.0
0.2.1
```

Phiên bản `0.y.z` thể hiện phần mềm đang ở giai đoạn phát triển ban đầu. Theo SemVer, public API trong giai đoạn này được xem là chưa ổn định; các thay đổi có thể xảy ra thường xuyên và không nhất thiết phải tuân theo cùng mức cam kết tương thích như từ `1.0.0` trở đi.

Điều này không có nghĩa nhóm phát triển nên tùy tiện phá API. Nếu đã có người dùng thử nghiệm hoặc tích hợp, việc thông báo breaking change, migration guide và release notes vẫn rất quan trọng. Một thư viện `0.x` được sử dụng rộng rãi vẫn có thể tạo chi phí nâng cấp lớn dù chưa có lời hứa ổn định chính thức.

Khi phát hành `1.0.0`, dự án tuyên bố public API đã đủ ổn định để bắt đầu cam kết tương thích theo SemVer. Đây là quyết định về chính sách và mức độ trưởng thành, không phải chỉ là đổi số 0 thành số 1.

## 5. Pre-release và build metadata

SemVer cho phép bổ sung thông tin sau phần `MAJOR.MINOR.PATCH`.

### 5.1. Pre-release version

Pre-release được thêm sau dấu gạch nối:

```text
2.5.0-alpha.1
2.5.0-beta.2
2.5.0-rc.1
```

Các nhãn phổ biến:

- `alpha`: bản thử nghiệm sớm, có thể còn thiếu tính năng hoặc thay đổi nhiều.
- `beta`: bản thử nghiệm rộng hơn, thường đã có phần lớn tính năng dự kiến.
- `rc` (release candidate): ứng viên phát hành, chỉ còn các vấn đề cần xử lý trước khi phát hành chính thức.

Tên nhãn chỉ là quy ước của dự án; SemVer không bắt buộc phải dùng đúng các tên này. Một pre-release có mức precedence thấp hơn phiên bản stable tương ứng:

```text
2.5.0-alpha.1 < 2.5.0-beta.1 < 2.5.0-rc.1 < 2.5.0
```

Pre-release hữu ích khi cần cho người dùng thử API trước khi phát hành ổn định. Không nên coi `2.5.0-rc.1` là tương đương `2.5.0`; nội dung hoặc API vẫn có thể thay đổi trước bản stable.

### 5.2. Build metadata

Build metadata được thêm sau dấu cộng:

```text
2.5.0+build.184
2.5.0+sha.a1b2c3
```

Metadata có thể ghi thông tin build number, commit hoặc pipeline. Theo SemVer, build metadata **không ảnh hưởng đến precedence**. Vì vậy:

```text
2.5.0+build.184
2.5.0+build.185
```

được xem là cùng mức precedence theo SemVer. Không nên dùng metadata như cách tăng version phát hành khi cần một thứ tự ưu tiên cao hơn.

### 5.3. Quy tắc so sánh phiên bản

SemVer so sánh trước tiên theo MAJOR, rồi MINOR, rồi PATCH. Nếu ba phần bằng nhau, pre-release được so sánh theo các định danh phân cách bằng dấu chấm. Định danh dạng số được so sánh theo giá trị số; định danh dạng chữ có quy tắc so sánh từ vựng; định danh số có precedence thấp hơn định danh không phải số tại vị trí tương ứng. Một phiên bản stable có precedence cao hơn pre-release cùng bộ ba số.

Ví dụ thứ tự:

```text
1.0.0-alpha
1.0.0-alpha.1
1.0.0-alpha.beta
1.0.0-beta
1.0.0-beta.2
1.0.0-beta.11
1.0.0-rc.1
1.0.0
```

Không nên tự so sánh version bằng cách tách chuỗi rồi so sánh từ điển. Ví dụ, chuỗi `1.10.0` có version lớn hơn `1.9.0`, dù nếu so sánh text đơn giản thì ký tự `1` ở phần minor có thể bị xếp trước `9` theo cách không mong muốn.

## 6. SemVer trong hệ sinh thái Java

SemVer thường được dùng cho thư viện Java, plugin và công cụ phát triển. Khi chọn dependency, người dùng cần hiểu version của artifact có ý nghĩa gì và công cụ build đang phân giải version theo quy tắc nào.

### 6.1. Version của thư viện Java

Một thư viện có thể phát hành:

```text
com.example:billing-core:2.4.7
```

Trong đó:

- `com.example` là group hoặc namespace phát hành.
- `billing-core` là artifact.
- `2.4.7` là version.

Người dùng khai báo dependency trong Gradle:

```kotlin
dependencies {
    implementation("com.example:billing-core:2.4.7")
}
```

Hoặc Maven:

```xml
<dependency>
  <groupId>com.example</groupId>
  <artifactId>billing-core</artifactId>
  <version>2.4.7</version>
</dependency>
```

Nếu nhà phát hành tuân thủ SemVer, người dùng có thể đọc version để ước lượng mức thay đổi. Nhưng công cụ build chỉ phân giải artifact theo version và quy tắc của nó; nó không tự kiểm chứng nhà phát hành đã tuân thủ lời hứa SemVer hay chưa.

### 6.2. Version của Gradle plugin

Gradle plugin cũng có version riêng, ví dụ:

```kotlin
plugins {
    id("com.example.code-quality") version "2.4.7"
}
```

Plugin version có thể tuân theo SemVer, nhưng ngoài API Java còn có giao diện build DSL:

- Plugin ID.
- Tên extension và cấu trúc cấu hình.
- Tên task và task property công khai.
- Kiểu task hoặc convention mà người dùng có thể tùy chỉnh.
- Phiên bản Gradle và JDK tối thiểu được hỗ trợ.

Ví dụ, đổi tên extension từ `quality` thành `verification` có thể phá build script của người dùng dù không có class Java nào bị xóa. Nếu extension cũ thuộc public API, thay đổi này thường là breaking change.

### 6.3. SemVer và quy tắc version của Maven/Gradle

SemVer là quy ước của nhà phát hành. Maven và Gradle có thuật toán, cú pháp constraint và quy tắc lựa chọn version riêng. Không nên giả định mọi version string trong repository đều được phân tích và sắp xếp chính xác theo toàn bộ SemVer 2.0.0.

Maven hỗ trợ khai báo version cụ thể và version range. Gradle hỗ trợ version constraint, rich version, dynamic selector và dependency resolution strategy. Cú pháp và quy tắc giải quyết của từng công cụ cần được đọc theo tài liệu của công cụ đó.

Ví dụ trong Gradle:

```kotlin
dependencies {
    implementation("com.example:billing-core:2.4.7")
}
```

Đây là khai báo version cụ thể, dễ truy nguyên hơn một dynamic selector như:

```kotlin
dependencies {
    implementation("com.example:billing-core:2.+")
}
```

`2.+` yêu cầu Gradle tìm một version phù hợp với selector theo quy tắc version resolution của Gradle. Nó không phải cú pháp SemVer để cam kết rằng mọi bản `2.x` đều tương thích, và kết quả có thể thay đổi khi repository xuất hiện version mới. Với build cần tái lập, nên ưu tiên version cụ thể hoặc dùng dependency constraints, version catalog, dependency locking và verification phù hợp.

## 7. Lời hứa tương thích có nhiều chiều

Khi nói một bản phát hành tương thích ngược, cần xác định tương thích theo chiều nào. Trong hệ sinh thái Java, ít nhất có các lớp sau:

| Loại tương thích | Câu hỏi cần trả lời | Ví dụ thay đổi có thể phá vỡ |
|---|---|---|
| Source compatibility | Mã nguồn khách hàng có tiếp tục biên dịch không? | Xóa method hoặc đổi kiểu tham số công khai. |
| Binary compatibility | Bytecode đã biên dịch trước đó có tiếp tục liên kết và chạy không? | Xóa method mà bytecode cũ tham chiếu, thay đổi class hierarchy theo cách không tương thích. |
| Behavioral compatibility | Chương trình có giữ hành vi đã tài liệu hóa không? | Thay đổi quy tắc làm tròn, thứ tự xử lý hoặc exception được ném ra. |
| Configuration compatibility | File cấu hình và DSL cũ có còn được chấp nhận không? | Đổi tên key cấu hình hoặc Gradle extension. |
| Runtime compatibility | Artifact có chạy trên môi trường Java và hệ điều hành đã cam kết không? | Nâng bytecode target hoặc dùng API chỉ có trên JDK mới. |
| Data/protocol compatibility | Dữ liệu đã lưu hoặc thông điệp trao đổi có còn đọc được không? | Thay schema database hoặc format message mà không có migration. |

SemVer không tự định nghĩa chi tiết mọi loại tương thích cho mọi sản phẩm. Dự án phải công bố những gì được bảo đảm. Một thư viện có thể cam kết source và binary compatibility nhưng không cam kết giữ nguyên hiệu năng, thời gian thực thi hoặc mọi hành vi nội bộ chưa được tài liệu hóa.

### 7.1. Source compatibility không giống binary compatibility

Source compatibility nói về việc biên dịch lại mã nguồn khách hàng. Binary compatibility nói về việc bytecode đã được biên dịch trước đó có thể liên kết với thư viện mới hay không.

Một thay đổi có thể vẫn biên dịch được sau khi khách hàng build lại nhưng lại làm bytecode cũ không chạy; cũng có trường hợp thay đổi overload khiến mã nguồn cũ trở nên mơ hồ dù một số bytecode đã biên dịch vẫn liên kết được. Do đó, kiểm tra compile một project mẫu chưa đủ để kết luận binary compatibility.

### 7.2. Behavioral compatibility khó xác định hơn

API có thể giữ nguyên chữ ký nhưng thay đổi hành vi. Ví dụ:

```java
public BigDecimal calculateFee(BigDecimal amount) {
    // Bản cũ làm tròn HALF_UP.
    // Bản mới chuyển sang HALF_EVEN.
}
```

Method vẫn có cùng tên, tham số và kiểu trả về, nhưng kết quả có thể khác với người dùng. Nếu quy tắc làm tròn đã được tài liệu hóa hoặc là một phần của hợp đồng sản phẩm, thay đổi đó có thể là breaking change về hành vi.

### 7.3. Tương thích runtime và JDK

Một thư viện có thể giữ nguyên API nhưng nâng yêu cầu runtime từ Java 17 lên Java 21. Ứng dụng chạy trên Java 17 sẽ không thể nạp class file có version mới hơn. Đây là breaking change đối với nhóm người dùng còn chạy Java 17, dù API Java của thư viện không thay đổi.

Nhà phát hành nên công bố:

- JDK tối thiểu để build thư viện.
- Java release target/bytecode của artifact.
- Các JDK/runtime được kiểm thử và hỗ trợ.
- Phiên bản Gradle hoặc Maven tối thiểu nếu plugin phụ thuộc vào build tool.

Việc dùng compiler JDK mới hơn không nhất thiết yêu cầu runtime mới hơn nếu dự án biên dịch với release target phù hợp. Nhưng lời hứa đó cần được kiểm tra cả dependency và runtime thực tế.

## 8. Những giới hạn của SemVer

SemVer hữu ích nhưng không phải hệ thống chứng minh tương thích. Có một số giới hạn quan trọng.

### 8.1. SemVer phụ thuộc vào cách định nghĩa public API

Nếu dự án không xác định rõ API nào được hỗ trợ, người dùng khó biết thay đổi nào là breaking. Một lớp public nội bộ có thể bị người dùng gọi trực tiếp dù dự án không hề muốn hỗ trợ nó. Ngược lại, DSL hoặc file format có thể là public contract nhưng không xuất hiện trong chữ ký Java.

Giải pháp là tài liệu hóa ranh giới API, đánh dấu internal/experimental, duy trì changelog và công bố chính sách deprecation.

### 8.2. SemVer không bảo đảm không có bug

Version `2.4.7` không chứng minh mọi bug đã được sửa hoặc không có regression. Nó chỉ thể hiện loại thay đổi mà nhà phát hành tuyên bố theo quy ước. Người dùng vẫn cần test và theo dõi issue.

### 8.3. SemVer không bảo đảm mọi dependency đều tương thích

Một thư viện có thể tuân thủ SemVer nhưng nâng dependency bắc cầu lên bản có hành vi khác hoặc yêu cầu JDK mới hơn. Người dùng cần xem dependency graph và kiểm tra runtime. Version của artifact trực tiếp không nói hết các thành phần được kéo theo.

### 8.4. SemVer không bảo đảm hiệu năng hoặc tài nguyên không đổi

Một bản minor có thể thêm tính năng và làm tăng bộ nhớ, thời gian khởi tạo hoặc số lượng thread. Nếu hiệu năng không nằm trong hợp đồng đã công bố, thay đổi đó có thể không được xem là breaking theo SemVer nhưng vẫn gây ảnh hưởng vận hành.

### 8.5. SemVer không bảo đảm dữ liệu hoặc giao thức có thể migration tự động

Một ứng dụng có thể dùng cùng API nhưng thay đổi schema database, cache format hoặc message protocol. Nếu những format đó được lưu trữ hoặc trao đổi qua nhiều phiên bản, cần chính sách migration riêng. Version number không tự chuyển đổi dữ liệu cũ.

### 8.6. SemVer không bảo đảm nhà phát hành thực sự tuân thủ

SemVer là quy ước do dự án lựa chọn. Công cụ build không kiểm tra tự động rằng bản `2.5.0` không có breaking change hoặc bản `2.4.8` chỉ sửa lỗi. Nếu nhà phát hành phân loại sai thay đổi, người dùng vẫn có thể gặp lỗi khi nâng cấp.

### 8.7. SemVer không định nghĩa thời gian hỗ trợ

Version không nói bản cũ sẽ được vá bảo mật trong bao lâu, khi nào hết hỗ trợ hoặc người dùng có bao nhiêu thời gian để migration. Đây là chính sách support/lifecycle riêng, cần công bố độc lập.

## 9. Quản lý breaking change bằng deprecation và migration

Để giảm rủi ro khi thay đổi API, dự án có thể dùng chu trình deprecation:

1. Đánh dấu API cũ là deprecated và cung cấp API thay thế.
2. Ghi rõ version dự kiến loại bỏ và hướng migration.
3. Duy trì API cũ trong một khoảng thời gian hoặc số major phù hợp với chính sách.
4. Phát hành breaking change trong major mới.
5. Cung cấp migration guide, ví dụ trước/sau và ghi chú về hành vi thay đổi.

Ví dụ Java:

```java
public class InvoiceClient {
    /**
     * @deprecated Use {@link #submit(Invoice, RequestOptions)} instead.
     */
    @Deprecated(since = "2.5.0", forRemoval = true)
    public Receipt submit(Invoice invoice) {
        return submit(invoice, RequestOptions.defaults());
    }

    public Receipt submit(Invoice invoice, RequestOptions options) {
        // Implementation mới.
        return new Receipt();
    }
}
```

Annotation `@Deprecated` giúp IDE và compiler phát cảnh báo cho người dùng. Các thuộc tính `since` và `forRemoval` có thể cung cấp thêm thông tin. Chúng không tự xóa API hoặc tự quyết định version MAJOR; nhà phát hành vẫn cần tuân theo chính sách tương thích của mình.

Migration guide nên giải thích:

- API hoặc cấu hình nào thay đổi.
- Vì sao thay đổi được thực hiện.
- Cách chuyển mã cũ sang mã mới.
- Thay đổi hành vi hoặc yêu cầu runtime nào cần chú ý.
- Cách kiểm thử sau khi nâng cấp.

## 10. Kiểm tra tương thích trước khi phát hành

Để lời hứa SemVer có cơ sở, cần đưa kiểm tra tương thích vào quy trình release.

### 10.1. Kiểm tra API và binary compatibility

Với thư viện Java, có thể dùng công cụ phân tích API/binary compatibility để so sánh public API giữa artifact hiện tại và artifact mới. Công cụ có thể phát hiện thay đổi như xóa method, đổi modifier, thay đổi hierarchy hoặc thay đổi signature.

Kiểm tra này không thay thế review hành vi. Nó chủ yếu phát hiện các thay đổi có thể quan sát ở cấu trúc API và bytecode.

### 10.2. Chạy test với phiên bản cũ và mới

Một chiến lược hữu ích là giữ một bộ test tương thích được chạy với:

- Artifact cũ để xác nhận test phản ánh hợp đồng đã công bố.
- Artifact mới để tìm regression.
- Các JDK/runtime thuộc phạm vi hỗ trợ.
- Các phiên bản framework hoặc dependency chính mà thư viện tuyên bố tương thích.

Với plugin build, nên có fixture project áp dụng plugin qua DSL thật và chạy task trên các phiên bản Gradle được hỗ trợ.

### 10.3. Kiểm tra dependency và runtime

Trước release, kiểm tra dependency tree, version constraints, dependency locking và Java release target. Một bản patch vẫn có thể gây vấn đề nếu kéo theo một dependency mới không tương thích hoặc thay đổi yêu cầu runtime.

### 10.4. Review changelog và version bump

Mỗi thay đổi cần được phân loại:

| Câu hỏi | Nếu câu trả lời là có |
|---|---|
| Có phá public API hoặc hợp đồng đã cam kết không? | Cân nhắc MAJOR. |
| Có thêm chức năng tương thích ngược không? | Cân nhắc MINOR. |
| Chỉ sửa lỗi tương thích ngược không? | Cân nhắc PATCH. |
| Có thay đổi runtime/JDK hoặc build tool tối thiểu? | Đánh giá xem đây có phải breaking change với nhóm người dùng hiện tại không. |
| Có thay đổi format dữ liệu hoặc cấu hình? | Xác định khả năng đọc dữ liệu cũ và yêu cầu migration. |

Không nên tự động chọn PATCH chỉ vì thay đổi được gọi là “bug fix”. Nếu sửa bug làm thay đổi hành vi mà người dùng đã dựa vào như một hợp đồng, cần đánh giá mức độ phá vỡ và công bố rõ.

## 11. Đọc version constraint một cách thận trọng

Người dùng dependency cần phân biệt version phát hành với khoảng version mà build chấp nhận.

Một version cụ thể:

```kotlin
implementation("com.example:billing-core:2.4.7")
```

giúp build chọn đúng bản được khai báo (còn phụ thuộc repository, metadata và dependency resolution). Một range hoặc dynamic selector cho phép công cụ chọn trong một tập phiên bản. Điều đó không đồng nghĩa mọi version trong tập đều tương thích theo SemVer.

Trong Gradle, có thể khai báo version constraint để mô tả giới hạn hoặc phiên bản mong muốn:

```kotlin
dependencies {
    implementation("com.example:billing-core") {
        version {
            strictly("[2.4, 3.0[")
        }
    }
}
```

Ví dụ này minh họa một khoảng version theo cú pháp Gradle; cách so sánh version cụ thể tuân theo cơ chế version ordering của Gradle và metadata được phân giải. Không nên coi nó là một bộ xác minh SemVer. Với môi trường cần tái lập, kết hợp version constraint với dependency locking hoặc version catalog theo chính sách của dự án.

Trong Maven, version range cũng có thể giới hạn tập phiên bản được chấp nhận. Tuy nhiên, range chỉ giúp chọn version theo metadata và quy tắc Maven; nó không kiểm tra public API hay chạy compatibility test. Với ứng dụng cần kết quả ổn định, version cụ thể thường dễ truy nguyên hơn range rộng.

## 12. Ví dụ xây dựng chính sách version cho thư viện Java

Giả sử nhóm phát hành thư viện `billing-core` và công bố hỗ trợ Java 17 trở lên. Chính sách có thể được viết như sau:

| Thành phần | Cam kết |
|---|---|
| Versioning | Tuân theo SemVer 2.0.0 từ `1.0.0`. |
| Public API | Package `com.example.billing` và các extension point được tài liệu hóa. |
| PATCH | Sửa lỗi tương thích ngược, không chủ ý thay đổi hợp đồng công khai. |
| MINOR | Thêm chức năng tương thích ngược; API cũ tiếp tục hoạt động. |
| MAJOR | Có thể xóa/đổi API hoặc thay đổi hợp đồng tương thích. |
| Java runtime | Artifact được biên dịch theo release 17; kiểm thử trên JDK 17 và các JDK LTS mới hơn trong phạm vi hỗ trợ. |
| Deprecation | Thông báo API sắp bỏ và cung cấp migration guide trước khi xóa khi có thể. |
| Support window | Quy định riêng thời gian vá lỗi và bảo mật cho từng major line. |

Các cam kết này giúp người dùng hiểu version có ý nghĩa gì. Nếu nhóm không muốn hỗ trợ binary compatibility hoặc không bảo đảm format dữ liệu, cần ghi rõ để tránh người dùng suy diễn quá mức từ SemVer.

## 13. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| Tăng MINOR nghĩa là không có thay đổi nào ảnh hưởng mã cũ. | MINOR cam kết tương thích ngược theo public API đã xác định; vẫn có thể có bug hoặc tương tác source-level cần kiểm tra. |
| PATCH chỉ được thay đổi vài dòng code. | PATCH được phân loại theo tác động tương thích, không theo kích thước diff. |
| Bất kỳ class `public` nào cũng phải được giữ mãi. | Dự án cần xác định public API được hỗ trợ; class nội bộ hoặc experimental có thể có chính sách khác nếu công bố rõ. |
| `0.x` có nghĩa là không cần changelog. | API chưa ổn định nhưng người dùng vẫn cần biết thay đổi và migration. |
| `2.+` có nghĩa là mọi version 2.x chắc chắn tương thích. | Dynamic selector chỉ chọn version theo quy tắc công cụ; không xác minh cam kết SemVer. |
| Cùng MAJOR nghĩa là mọi runtime đều tương thích. | Cần kiểm tra source, binary, behavior, JDK, configuration và dependency. |
| Build metadata làm version mới hơn. | Build metadata không ảnh hưởng precedence theo SemVer. |
| Version stable đồng nghĩa không có bug. | Stable chỉ nói về trạng thái phát hành; không phải bảo đảm chất lượng tuyệt đối. |

## 14. Nguyên tắc áp dụng SemVer trong dự án Java

- Xác định và tài liệu hóa public API trước khi cam kết versioning.
- Phân loại thay đổi theo tác động đến source, binary, behavior, configuration và runtime.
- Dùng PATCH cho sửa lỗi tương thích ngược, MINOR cho tính năng tương thích ngược và MAJOR cho breaking change.
- Công bố rõ chính sách cho version `0.x`, pre-release và API experimental.
- Dùng deprecation và migration guide để chuẩn bị cho breaking change.
- Kiểm tra API/binary compatibility, test behavior và runtime trước khi phát hành.
- Kiểm tra dependency bắc cầu, Java release target và yêu cầu build tool.
- Không dựa vào version range hoặc dynamic selector như bằng chứng tương thích.
- Công bố support window, security policy và thời gian maintenance riêng với SemVer.
- Viết release notes mô tả thay đổi quan sát được, kể cả khi version bump chỉ là PATCH.

SemVer giúp nhà phát hành truyền đạt loại thay đổi mà người dùng có thể kỳ vọng khi nâng cấp. MAJOR báo hiệu có thể có breaking change, MINOR báo hiệu bổ sung tương thích ngược và PATCH báo hiệu sửa lỗi tương thích ngược. Nhưng lời hứa đó chỉ rõ ràng khi dự án định nghĩa public API, các chiều tương thích, runtime được hỗ trợ và quy trình kiểm tra. Trong build Java, version number là tín hiệu để ra quyết định; dependency resolution, compatibility tests, changelog và chính sách hỗ trợ mới cung cấp bằng chứng để nâng cấp an toàn.
