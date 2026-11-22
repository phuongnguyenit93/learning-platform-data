# Quy tắc phù hợp với phiên bản ngôn ngữ và kiểu mô-đun

## 1. Mục tiêu bài học

Trong chương **Quy ước và nhất quán** thuộc module **CODE_QUALITY_FUNDAMENTALS**, chúng ta xem xét cách xây dựng quy tắc viết mã Java **phù hợp với phiên bản ngôn ngữ, môi trường chạy và vai trò của mô-đun**. Quy ước tốt không chỉ làm các tệp trông giống nhau: nó phải giúp mã biên dịch được ở môi trường cần hỗ trợ, thể hiện đúng ranh giới phụ thuộc và giữ được hợp đồng mà thành phần khác sử dụng.

Module có mục tiêu **hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không**. Một quy ước chọn sai bối cảnh có thể khiến thư viện không chạy trên JDK của khách hàng, làm lộ lớp nội bộ hoặc buộc cả ứng dụng dùng cấu trúc quá phức tạp. Ngược lại, quy ước có phạm vi rõ ràng tạo ra sự nhất quán **có ý nghĩa**, thay vì bắt mọi tệp phải giống nhau bất kể nhiệm vụ.

Sau bài học, bạn có thể:

- Phân biệt **phiên bản cú pháp Java**, **API của thư viện chuẩn**, **JDK biên dịch** và **JVM chạy ứng dụng**.
- Giải thích vì sao quy tắc dùng `record`, `sealed`, `var` hoặc API mới cần phù hợp với Java release mục tiêu.
- Phân biệt mô-đun theo **công cụ build**, mô-đun **JPMS** và mô-đun theo **trách nhiệm kiến trúc**.
- Chọn quy ước phù hợp cho thư viện dùng chung, ứng dụng triển khai, adapter tích hợp và mã kiểm thử.
- Đọc ví dụ Java 17 về một thư viện có hợp đồng công khai và phần triển khai nội bộ, kèm kiểm thử hành vi.
- Xác định khi nào nên thống nhất quy tắc toàn repository và khi nào cần ngoại lệ có phạm vi, có lý do.

## 2. Hai câu hỏi phải trả lời trước khi chọn quy ước

Trước khi đề xuất “từ nay tất cả lớp dữ liệu dùng `record`” hoặc “mọi package đều phải `exports`”, cần biết:

1. **Đoạn mã phải hoạt động ở phiên bản Java và môi trường nào?** JDK nào biên dịch, bytecode và API chuẩn nào được cho phép, JVM nào phải chạy được?
2. **Đoạn mã đang thuộc loại mô-đun nào?** Một thư viện công khai dùng chung, một ứng dụng được triển khai riêng, một adapter phụ thuộc framework, mã kiểm thử hay một JPMS named module?

Ví dụ, Java 17 hỗ trợ `record`, nhưng một thư viện phải chạy trên Java 11 **không thể** đưa `record` vào API công khai rồi kỳ vọng người dùng Java 11 sử dụng bình thường. Ngược lại, khi toàn bộ ứng dụng chắc chắn dùng Java 17, cấm mọi `record` chỉ vì một mô-đun khác trong repository còn hỗ trợ Java 11 có thể khiến code dài và khó hiểu không cần thiết.

Tương tự, quy tắc “không dùng annotation của framework trong mô hình miền nghiệp vụ” có thể có ích với **thư viện tính toán thuần**, nhưng một **adapter tích hợp HTTP/JSON** được tạo ra chính để tương tác với framework và hợp đồng ngoài hệ thống. Cần biết ranh giới trước khi đánh giá mã có nhất quán không.

| Trục quyết định | Ví dụ cần xác nhận | Ảnh hưởng đến quy ước |
| --- | --- | --- |
| **Language level** | Java 11, 17 hay 21? | Cú pháp, kiểu dữ liệu và tính năng được phép dùng. |
| **JDK API level** | API chuẩn từ bản Java nào? | Phương thức/lớp thư viện chuẩn có dùng được ở runtime mục tiêu không? |
| **Môi trường build/runtime** | Dùng JDK mới hơn để biên dịch cho runtime cũ? | Cần cấu hình release và kiểm tra tương thích thực tế. |
| **Loại mô-đun** | Library, application, adapter, test | Quy tắc công khai API, tiêm phụ thuộc, tài nguyên và framework khác nhau. |
| **Ranh giới module** | Build subproject hay JPMS named module? | Cách biểu diễn phụ thuộc, export package và đóng gói. |
| **Vòng đời phát hành** | Thư viện dùng chung hay ứng dụng triển khai một lần? | Mức độ bảo vệ tương thích API, chính sách nâng cấp và versioning. |

## 3. Quy ước phải phù hợp với phiên bản Java mục tiêu

### 3.1. Một số mốc tính năng có ý nghĩa

| Phiên bản Java | Ví dụ tính năng đã có ở phiên bản đó | Ý nghĩa khi đặt quy ước |
| --- | --- | --- |
| **Java 8** | Lambda, method reference, Stream API | Có thể chọn vòng lặp hoặc stream theo khả năng đọc và bài toán. |
| **Java 11** | `var` cho biến cục bộ (có từ Java 10); HTTP Client chuẩn ở Java 11 | Một dự án nhắm Java 11 có thể dùng các tính năng này nhưng chưa thể dùng `record`. |
| **Java 17** | `record` (ổn định từ Java 16), `sealed` (ổn định ở Java 17), pattern matching cho `instanceof` (ổn định từ Java 16) | Có thể đơn giản hóa mô hình giá trị và phân cấp kiểu khi đúng ngữ nghĩa. |
| **Java 21** | Virtual threads, pattern matching cho `switch` (tính năng chính thức ở Java 21) | Chỉ dùng trong phần mã mà môi trường mục tiêu thực sự hỗ trợ. |

Bảng minh họa những khả năng **được phép về mặt phiên bản**, không khẳng định rằng dùng tính năng mới luôn tốt hơn.

Chẳng hạn, `record` phù hợp với một kiểu dữ liệu mang giá trị và không cần sửa các thành phần sau khởi tạo. Nó **không tự bất biến sâu** nếu chứa đối tượng mutable. Dùng `record` cho một entity có vòng đời và thay đổi nội tại phức tạp chỉ vì “đang ở Java 17” có thể làm mô hình khó hiểu hơn.

Tương tự, `sealed` hữu ích khi miền nghiệp vụ thật sự có một tập loại biến thể được kiểm soát. Không cần biến mọi interface dùng chung thành `sealed` nếu ứng dụng cần cho phép adapter mới do mô-đun khác cung cấp.

### 3.2. Không nhầm phiên bản compiler với mục tiêu tương thích

Chạy lệnh `java -version` trên máy phát triển cho biết phiên bản Java đang có ở môi trường đó; nó **không** tự xác nhận phiên bản sản phẩm phải hỗ trợ. Khi build với JDK mới hơn, mã vẫn có thể vô tình sử dụng cú pháp hoặc API không tồn tại ở runtime cũ.

Với công cụ `javac` hỗ trợ tùy chọn `--release`, việc đặt:

```text
javac --release 17 ...
```

giúp biên dịch mã theo mức ngôn ngữ, bytecode và tập API nền tảng của **Java 17**. Đây là **ví dụ minh họa tùy chọn compiler**, không phải lệnh build cho repository đang học. Công cụ build như Maven hoặc Gradle thường có cách cấu hình toolchain/release tương ứng.

`--release` cũng **không tự bảo đảm toàn bộ ứng dụng chạy đúng**: các thư viện phụ thuộc có thể được build cho phiên bản mới hơn; cấu hình runtime, native code, JPMS, hệ điều hành và hành vi tích hợp vẫn cần kiểm thử trong môi trường mục tiêu.

Nên thống nhất **mức tương thích của từng artifact** và làm cho CI kiểm tra nó. Không để một file build ghi Java 11 nhưng style guide lại mặc định dùng `record` hoặc API chỉ tồn tại từ Java 17.

### 3.3. Tính năng preview cần chính sách riêng

Một số cú pháp xuất hiện dưới dạng **preview** trước khi trở thành tính năng chính thức. Quy tắc “đang dùng JDK này nên tính năng nào cũng có thể dùng” là không an toàn: preview có thể cần cờ biên dịch/chạy riêng, thay đổi ngữ nghĩa giữa các phiên bản và tăng gánh nặng nâng cấp.

Với thư viện được nhiều dự án sử dụng, một chính sách thận trọng là **không đưa preview feature vào hợp đồng công khai** khi chưa có lý do và cam kết tương thích rõ ràng. Với ứng dụng thử nghiệm có kiểm soát, nhóm có thể cho phép preview theo phạm vi xác định, tài liệu hóa điều kiện bật tính năng và cách nâng cấp. Quy tắc cần phản ánh **vòng đời triển khai**, không chỉ sự hấp dẫn của cú pháp mới.

## 4. “Mô-đun” có thể mang nhiều nghĩa

Từ *module* trong dự án Java có thể chỉ các khái niệm khác nhau. Nhầm chúng với nhau dễ dẫn đến quy ước không áp dụng được.

### 4.1. Mô-đun trong công cụ build

Một **Maven module** hoặc **Gradle subproject** là đơn vị cấu hình build, phụ thuộc và artifact theo công cụ tương ứng. Ví dụ một repository có các subproject `shipping-core`, `shipping-adapter-db` và `shop-app`.

Chúng có thể được build bằng những mức tương thích khác nhau nếu quy trình phát hành cho phép. **Có nhiều Gradle subproject không đồng nghĩa toàn bộ chúng là named module của JPMS.**

### 4.2. Mô-đun theo Java Platform Module System (JPMS)

JPMS được giới thiệu trong Java 9, dùng descriptor `module-info.java` để khai báo một **named module**, những module nó phụ thuộc (`requires`) và package được cung cấp cho module khác (`exports`). Một package không được export sẽ không phải API công khai có thể truy cập từ named module khác theo quy tắc module path thông thường.

JPMS là **cơ chế runtime và biên dịch của Java**, không chỉ cách chia thư mục. Chạy trên **classpath** và chạy trên **module path** có các quy tắc đóng gói khác nhau; có tệp `module-info.java` chưa đủ để kết luận mọi môi trường triển khai đều đang thực thi ranh giới JPMS.

Ngoài `exports`, các framework dùng reflection có thể cần cấu hình `opens` cho package phù hợp. Chỉ mở package có nhu cầu thực tế; không mở toàn bộ module chỉ vì một lỗi reflection mà chưa hiểu nguyên nhân.

### 4.3. Mô-đun theo trách nhiệm kiến trúc

Trong thiết kế, *module* cũng có thể chỉ một phần chịu trách nhiệm cho một nhóm hành vi: **domain**, **application service**, **adapter**, **API contract**, **test support**. Ranh giới này **có thể** trùng với subproject hoặc named module, nhưng không bắt buộc.

Ví dụ, một thư viện đơn giản gồm package `api` và `internal` trong cùng artifact vẫn có thể có trách nhiệm rõ ràng. Ngược lại, chia thành mười subproject chưa bảo đảm rằng các phụ thuộc đã được định hướng đúng.

| Khái niệm | Công cụ hoặc cơ chế biểu diễn | Câu hỏi trọng tâm |
| --- | --- | --- |
| Build subproject | Maven/Gradle | Build và phát hành những artifact nào? |
| JPMS named module | `module-info.java`, module path | Module nào được phép đọc/phụ thuộc; package nào được export/mở? |
| Logical/architectural module | Package, API, cấu trúc mã, quy ước phụ thuộc | Trách nhiệm nào nằm cùng nhau, thứ gì được phép biết về thứ khác? |

**Quy ước tốt phải nói rõ đang áp dụng cho loại module nào.** Quy tắc “mọi module phải có `module-info.java`” chỉ có nghĩa nếu dự án thực sự quyết định dùng JPMS và có kế hoạch tương thích với thư viện/framework liên quan.

## 5. Quy ước theo vai trò của mô-đun

Một repository có thể có nhiều loại thành phần nhưng vẫn giữ một bộ **nguyên tắc chung**: tên rõ nghĩa, xử lý lỗi đúng hợp đồng, kiểm thử có ý nghĩa, format thống nhất. Những **quy tắc cụ thể** nên khác nhau khi lý do tồn tại của thành phần khác nhau.

| Vai trò | Ưu tiên chính | Quy ước có thể phù hợp | Điều không nên áp đặt máy móc |
| --- | --- | --- | --- |
| **Library/API dùng chung** | Hợp đồng ổn định, tương thích, ít phụ thuộc không cần thiết | Chỉ công bố kiểu cần thiết; mô tả input/output/lỗi; kiểm soát mức Java thấp nhất phải hỗ trợ | Dùng cú pháp mới làm phá người dùng cũ chỉ để giảm số dòng |
| **Domain/core** | Biểu diễn đúng quy tắc nghiệp vụ; dễ thử độc lập | Ưu tiên kiểu dữ liệu và hàm có ý nghĩa; hạn chế phụ thuộc I/O/framework nếu không cần | Bắt mọi domain class kế thừa base class của framework |
| **Ứng dụng triển khai** | Lắp ghép các thành phần, cấu hình và hành vi đầu cuối | Composition root rõ; quản lý lifecycle, timeout, log/metric | Đòi tính ổn định API tương tự thư viện công khai cho mọi helper nội bộ |
| **Adapter tích hợp** | Tương thích giao thức/framework bên ngoài | Giữ cấu trúc payload ở ranh giới; ánh xạ về hợp đồng nội bộ; làm rõ lỗi và tài nguyên | Cấm tất cả annotation hoặc kiểu đặc thù của framework |
| **Mã kiểm thử** | Tạo bằng chứng lặp lại được, dễ đọc | Tên test theo hành vi; dữ liệu cố định; fake/fixture có phạm vi | Bắt fixture hoặc test helper phải có mức API ổn định như library phân phối |
| **Mã được sinh (generated)** | Khớp generator và định dạng hợp đồng nguồn | Sửa generator/template hoặc quy trình sinh khi cần | Bắt chỉnh tay mọi tệp generated rồi để lần sinh kế tiếp ghi đè |

**Tính nhất quán không phải đồng nhất tuyệt đối.** Một thư viện dùng chung và ứng dụng chạy nó có thể chia sẻ chuẩn code style nhưng **khác mức Java**, **khác yêu cầu tương thích** và **khác nơi sử dụng framework**. Ngoại lệ cần được diễn đạt thành một chính sách có phạm vi, không thành “mỗi nhóm tự làm theo ý thích”.

## 6. Ví dụ Java 17: hợp đồng thư viện và phần triển khai nội bộ

Giả sử một nhóm xây dựng **thư viện tính phí vận chuyển** để nhiều ứng dụng dùng. Các ứng dụng được phép biết yêu cầu đầu vào và kết quả báo giá, nhưng không cần biết ngưỡng miễn phí đang đặt ở đâu.

Ràng buộc của ví dụ:

- Artifact của thư viện có **mức Java mục tiêu là 17**.
- Đơn vị tiền là **VND nguyên**, biểu diễn bằng `long`.
- `subtotalVnd` không âm. Dưới **500.000 VND**, khách thường trả **30.000 VND**, thành viên trả **15.000 VND**; từ 500.000 VND trở lên miễn phí.
- Tổng là tổng tiền hàng cộng phí; phép cộng tràn `long` phải bị phát hiện.
- Chỉ package `api` là hợp đồng dành cho ứng dụng khác; cách tính cụ thể là **chi tiết nội bộ**.

Đây là một ví dụ tách vai trò giữa **công bố API** và **cài đặt**, không phải yêu cầu mọi ứng dụng nhỏ đều phải dựng cấu trúc như vậy.

### 6.1. Kiểu dữ liệu công khai dùng tính năng ổn định trong Java 17

```java
// com/example/shop/shipping/api/ShippingRequest.java
package com.example.shop.shipping.api;

public record ShippingRequest(long subtotalVnd, boolean member) {
    public ShippingRequest {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException(
                    "subtotalVnd must not be negative");
        }
    }
}
```

```java
// com/example/shop/shipping/api/ShippingQuote.java
package com.example.shop.shipping.api;

public record ShippingQuote(
        long subtotalVnd, long shippingFeeVnd, long totalVnd) {
    public ShippingQuote {
        if (subtotalVnd < 0 || shippingFeeVnd < 0) {
            throw new IllegalArgumentException(
                    "subtotal and shipping fee must be non-negative");
        }
        if (Math.addExact(subtotalVnd, shippingFeeVnd) != totalVnd) {
            throw new IllegalArgumentException(
                    "totalVnd must equal subtotalVnd + shippingFeeVnd");
        }
    }
}
```

`record` trong Java 17 biểu diễn các thành phần rõ ràng và cung cấp accessor, `equals`, `hashCode` và `toString` theo giá trị các thành phần. Constructor gọn được dùng để kiểm tra **bất biến hợp đồng**. Với các thành phần kiểu nguyên thủy trong ví dụ, không có đối tượng mutable nằm bên trong.

Không nên suy ra từ đây rằng **mọi public API đều phải là record**. Nếu dữ liệu cần thay đổi từng phần, có quan hệ kế thừa cụ thể, hoặc framework tiêu thụ API đòi quy tắc khác, nhóm cần đánh giá hợp đồng thay vì rập khuôn.

### 6.2. Quy tắc tính phí thuộc nội bộ thư viện

```java
// com/example/shop/shipping/internal/StandardShippingPolicy.java
package com.example.shop.shipping.internal;

import com.example.shop.shipping.api.ShippingRequest;

public final class StandardShippingPolicy {
    private static final long FREE_FROM_VND = 500_000;
    private static final long MEMBER_FEE_VND = 15_000;
    private static final long REGULAR_FEE_VND = 30_000;

    private StandardShippingPolicy() {}

    public static long feeVnd(ShippingRequest request) {
        if (request.subtotalVnd() >= FREE_FROM_VND) {
            return 0;
        }
        return request.member()
                ? MEMBER_FEE_VND : REGULAR_FEE_VND;
    }
}
```

`StandardShippingPolicy` được khai báo `public` để lớp ở package `api` có thể gọi từ package khác. **`public` ở cấp Java không đồng nghĩa package đó phải được export từ named module JPMS**. Khi thư viện chạy như named module và chỉ export package `api`, module tiêu thụ không thể nhập trực tiếp lớp từ package `internal` theo ranh giới JPMS thông thường.

Ở dự án chỉ dùng classpath, ranh giới `exports` không được thực thi theo cùng cách; vì vậy package `internal` vẫn cần **quy ước và kỷ luật phụ thuộc**. Không nên coi tên package `internal` tự tạo cơ chế bảo mật hay ẩn hoàn toàn mọi lớp.

### 6.3. API công khai giữ nhiệm vụ rõ ràng

```java
// com/example/shop/shipping/api/ShippingQuotes.java
package com.example.shop.shipping.api;

import java.util.Objects;
import com.example.shop.shipping.internal.StandardShippingPolicy;

public final class ShippingQuotes {
    private ShippingQuotes() {}

    public static ShippingQuote quote(ShippingRequest request) {
        Objects.requireNonNull(request, "request");

        long feeVnd = StandardShippingPolicy.feeVnd(request);
        long totalVnd = Math.addExact(request.subtotalVnd(), feeVnd);

        return new ShippingQuote(
                request.subtotalVnd(), feeVnd, totalVnd);
    }
}
```

`ShippingQuotes` cung cấp năng lực **lấy báo giá** mà ứng dụng cần. Nó không buộc caller tự tạo `StandardShippingPolicy` hay hiểu hằng số ngưỡng. Bất biến đầu vào, đơn vị tiền và phản ứng khi tràn số thể hiện trong hợp đồng.

Đây là thư viện thuần, tính toán đồng bộ và không có I/O. Nếu quy tắc thay đổi theo cấu hình hoặc được lấy từ mạng, việc thêm dependency, cache hoặc đồng hồ phải đi kèm **hợp đồng mới về tính nhất quán, lỗi và thời điểm tính**. Không nên che giấu tác dụng phụ mới chỉ để giữ nguyên chữ ký phương thức.

### 6.4. JPMS: export API, giữ phần nội bộ không export

Nếu dự án thực sự dùng JPMS trên module path, một descriptor **minh họa** có thể là:

```java
// module-info.java của thư viện, không phải file cần tạo trong bài học
module com.example.shop.shipping {
    exports com.example.shop.shipping.api;
}
```

Module này không khai báo `exports com.example.shop.shipping.internal;`. Ứng dụng tiêu thụ dưới dạng named module có thể khai báo:

```java
// module-info.java của một ứng dụng tiêu thụ, minh họa riêng
module com.example.shop.checkout {
    requires com.example.shop.shipping;
}
```

Đoạn mã trên là **hai descriptor ở hai module khác nhau**, không được đặt cạnh nhau trong một tệp `module-info.java`. Mô-đun ứng dụng dùng kiểu công khai trong package `api` và không thể phụ thuộc trực tiếp package `internal` theo cơ chế export JPMS.

JPMS không thay thế việc thiết kế hợp đồng đúng: nếu package `api` trả ra một kiểu nằm trong package không export, caller vẫn có thể gặp vấn đề sử dụng. Ngoài ra, nhiều framework sử dụng reflection cần cấu hình `opens` cho package thích hợp; `exports` và `opens` phục vụ hai loại truy cập khác nhau, nên không tự động mở tất cả package.

## 7. Kiểm thử hợp đồng và ranh giới phiên bản

Trong phạm vi Java 17, bài kiểm thử JUnit 5 có thể bảo vệ hành vi nghiệp vụ mà không gọi trực tiếp lớp `internal`. Ví dụ:

```java
// ShippingQuotesTest.java trong test sources
package com.example.shop.shipping.api;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class ShippingQuotesTest {
    @Test
    void standardMemberFeeAppliesBelowThreshold() {
        ShippingQuote result = ShippingQuotes.quote(
                new ShippingRequest(499_999, true));

        assertEquals(
                new ShippingQuote(499_999, 15_000, 514_999),
                result);
    }

    @Test
    void shippingIsFreeAtThreshold() {
        assertEquals(
                new ShippingQuote(500_000, 0, 500_000),
                ShippingQuotes.quote(new ShippingRequest(500_000, false)));
    }

    @Test
    void regularCustomerPaysFeeForEmptySubtotal() {
        assertEquals(
                new ShippingQuote(0, 30_000, 30_000),
                ShippingQuotes.quote(new ShippingRequest(0, false)));
    }

    @Test
    void invalidValueAndOverflowAreRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> new ShippingRequest(-1, false));
        assertThrows(ArithmeticException.class,
                () -> new ShippingQuote(Long.MAX_VALUE, 1, 0));
    }
}
```

Các test xác nhận ngưỡng **499.999/500.000 VND**, phí khách thường, bất biến đầu vào và việc không cho xây dựng một `ShippingQuote` có phép cộng tràn `long`. Điều này **không** chứng minh toàn bộ tương thích thư viện: còn cần kiểm tra cách đóng gói artifact, công cụ build, các dependency và việc tiêu thụ từ module khác.

Nếu test đặt bên cạnh một named module JPMS, cách chạy JUnit có thể cần cấu hình module path, mở package cho test framework hoặc `--patch-module` tùy thiết lập build. **Không sửa `module-info.java` một cách ngẫu nhiên chỉ để test chạy**; hãy thiết lập và tài liệu hóa chính sách test JPMS phù hợp với môi trường của dự án.

Đặc biệt, nếu người dùng thư viện có yêu cầu chạy ở **Java 11**, ví dụ dùng `record` trên không đáp ứng mục tiêu. Kiểm thử nghiệp vụ dù đều xanh trên JDK 17 **không biến bytecode hoặc API Java 17 thành tương thích Java 11**.

## 8. Nếu phải hỗ trợ Java 11, quy tắc biểu diễn dữ liệu cần thay đổi

Với một thư viện nhắm Java 11, `record` chưa phải cú pháp được hỗ trợ. Khi đó, một kiểu giá trị tương đương về **dữ liệu và bất biến** có thể được viết bằng lớp `final` với trường `private final` và constructor kiểm tra đầu vào.

Ví dụ **thay thế** `ShippingRequest` của phần Java 17 (không đưa hai định nghĩa cùng tên vào một artifact):

```java
// ShippingRequest.java - biến thể tương thích Java 11
package com.example.shop.shipping.api;

public final class ShippingRequest {
    private final long subtotalVnd;
    private final boolean member;

    public ShippingRequest(long subtotalVnd, boolean member) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException(
                    "subtotalVnd must not be negative");
        }
        this.subtotalVnd = subtotalVnd;
        this.member = member;
    }

    public long subtotalVnd() {
        return subtotalVnd;
    }

    public boolean member() {
        return member;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof ShippingRequest)) return false;
        ShippingRequest that = (ShippingRequest) other;
        return subtotalVnd == that.subtotalVnd
                && member == that.member;
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hash(subtotalVnd, member);
    }

    @Override
    public String toString() {
        return "ShippingRequest[subtotalVnd=" + subtotalVnd
                + ", member=" + member + "]";
    }
}
```

Các accessor được **cố ý giữ tên** `subtotalVnd()` và `member()` trong ví dụ để minh họa API của `record`, nhưng một dự án Java 11 đã công bố kiểu JavaBean với `getSubtotalVnd()`/`isMember()` có thể có yêu cầu tương thích khác. **Hợp đồng công khai quyết định tên cần giữ**, không phải sở thích của người refactor.

Nếu chuyển toàn bộ thư viện xuống Java 11, `ShippingQuote` cũng phải được thay bằng một kiểu mà Java 11 hỗ trợ; chỉ thay `ShippingRequest` là chưa đủ. Cần kiểm thử lại giá trị, `equals`/`hashCode`, serialization nếu có, API binary và cách framework sử dụng kiểu dữ liệu.

**Bài học về quy ước:** hai biến thể có thể cùng tuân thủ nguyên tắc **giá trị hợp lệ, không bị sửa ngoài ý muốn, tên công khai rõ nghĩa** nhưng **khác cú pháp và cách triển khai**. Sự nhất quán nằm ở **bảo đảm và phạm vi hỗ trợ**, không nhất thiết ở việc mọi tệp đều dùng một từ khóa.

## 9. Thiết kế quy tắc cho từng module mà không làm phân mảnh repository

Một chính sách hiệu quả thường gồm hai lớp:

### 9.1. Quy tắc chung cho toàn repository

Ví dụ:

- Tên thể hiện ý nghĩa, không dùng từ viết tắt khó hiểu ngoài bối cảnh.
- Format được công cụ tự động áp dụng theo cấu hình nhất quán.
- Mọi public API có hợp đồng input, output, lỗi và tác dụng phụ rõ.
- Không đưa bí mật vào mã nguồn hoặc log; xử lý tài nguyên đúng vòng đời.
- Test phải kiểm chứng hành vi thực và trường hợp biên quan trọng.
- Đường phụ thuộc phải có lý do: phần miền nghiệp vụ không tự động phụ thuộc framework chỉ vì các adapter đang dùng nó.

### 9.2. Ngoại lệ theo phạm vi được ghi rõ

| Phạm vi | Quy tắc hoặc ngoại lệ hợp lý | Lý do cần ghi |
| --- | --- | --- |
| `legacy-client-api` nhắm Java 11 | Không dùng record/sealed trong mã nguồn build cho Java 11 | Giữ mức Java hỗ trợ đã công bố. |
| `shipping-core` nhắm Java 17 | Có thể dùng record cho giá trị; tránh rò rỉ framework vào lõi | Đơn giản hóa mô hình và giảm phụ thuộc. |
| `web-adapter` | Cho phép annotation, DTO và tên trường giao thức tại adapter | Tương thích framework/API ngoài. |
| `shop-app` | Có cấu hình injection, tài nguyên và monitoring theo runtime | Đó là trách nhiệm của ứng dụng triển khai. |
| `test-support` | Cho phép fake và fixture có API nội bộ nhỏ | Phục vụ kiểm thử, không phải thư viện công khai vĩnh viễn. |
| `generated-sources` | Quy tắc kiểm tra tập trung ở generator và đầu ra | Tránh sửa tay bị ghi đè khi sinh lại. |

Tên subproject ở bảng là **ví dụ giả định**, không mô tả cấu trúc thực tế của repository. Điều quan trọng là khi người đọc mở một tệp, họ biết **quy tắc chung nào áp dụng và ngoại lệ nào được cho phép tại phạm vi ấy**.

Một chính sách tốt tránh hai cực đoan:

1. **Một chuẩn duy nhất không xét bối cảnh:** vô tình cấm khả năng hữu ích của Java 17 hoặc phá tương thích của thư viện Java 11.
2. **Mỗi nhóm tự có chuẩn riêng:** cùng một kiểu trách nhiệm nhưng dùng cách đặt tên, lỗi và tổ chức hoàn toàn khác nhau, gây khó bảo trì.

Khi ngoại lệ trở thành phổ biến, cần xem lại liệu quy tắc chung có đang sai phạm vi, thay vì thêm ngày càng nhiều “trường hợp đặc biệt” không ai còn nhớ.

## 10. Quy tắc phải được thực thi bằng build, công cụ và kiểm thử

Một tài liệu style guide có giá trị hơn khi có **cơ chế phản hồi**. Tuy vậy, mỗi công cụ kiểm tra được một loại quy tắc khác nhau:

| Cơ chế | Có thể kiểm tra | Không tự kết luận |
| --- | --- | --- |
| Compiler với release phù hợp | Cú pháp, bytecode và API nền tảng theo Java target | Dependency bên ngoài và môi trường thật đều tương thích. |
| Formatter/linter | Format, import, tên và một số quy ước mã | Thiết kế module có đúng trách nhiệm nghiệp vụ không. |
| Static analysis | Một số mẫu lỗi hoặc cấu trúc đáng nghi | Mọi API hay quy tắc nghiệp vụ đều đúng. |
| Kiểm tra dependency/package | Một số chiều phụ thuộc hoặc việc dùng package không được phép | Runtime reflection và toàn bộ hành vi tích hợp. |
| Unit test | Hành vi đã chọn, bất biến, trường hợp biên | Artifact có chạy trên JVM mục tiêu hoặc module path mục tiêu không. |
| Integration/compatibility test | Tương thích artifact, JPMS/classpath, framework và các phần phụ thuộc thật | Đã kiểm tra mọi tổ hợp có thể có chưa. |
| Code review | Ngữ nghĩa và ngoại lệ có hợp lý không | Tự động phát hiện mọi sai sót khi không có bằng chứng. |

Một **bộ kiểm tra tối thiểu** với thư viện dùng chung có thể gồm:

1. Build ở mức `--release` đã công bố, tránh vô tình dùng API JDK mới hơn.
2. Kiểm tra rằng các dependency không đòi runtime cao hơn mức mà thư viện cam kết.
3. Chạy unit test bảo vệ hợp đồng công khai và kiểm thử biên.
4. Kiểm thử tiêu thụ artifact từ một dự án mẫu với **runtime mục tiêu** và cách chạy thực tế (classpath/JPMS module path).
5. Nếu dùng JPMS, kiểm tra package API được export đúng, package nội bộ không bị truy cập sai và reflection của adapter chạy theo cấu hình.
6. Review thay đổi public API và chính sách tương thích trước khi phát hành.

Đây là **quy trình gợi ý**, không khẳng định bất kỳ bước nào đã chạy trong repository. Chạy build, kiểm thử tự động và kiểm tra hiện thực là nhiệm vụ triển khai/QA riêng; viết được quy ước chưa đồng nghĩa đã chứng minh toàn bộ chất lượng mã.

## 11. Khi nâng phiên bản Java hoặc đổi ranh giới mô-đun

Một đợt nâng từ Java 11 sang Java 17 **không nên** chỉ là thay con số trong file build và thay hàng loạt class thành record. Cần xác định rõ:

1. **Artifact nào cần hỗ trợ Java 11 tiếp?** Nếu thư viện vẫn có người dùng cũ, có thể phải giữ target Java 11 dù ứng dụng chính chuyển lên Java 17.
2. **Những API công khai nào đang được tiêu thụ?** Đổi từ class sang record có thể làm thay đổi constructor, accessor, khả năng kế thừa, serialization hoặc binary compatibility.
3. **Framework/dependency đã tương thích chưa?** Kiểm tra bytecode, reflection, annotation processing và runtime thực.
4. **Quy tắc nào nên thay đổi, quy tắc nào giữ nguyên?** Chỉ thêm record/sealed tại nơi chúng làm ý nghĩa rõ hơn và không phá hợp đồng.
5. **Module path hay classpath?** Nếu chuyển sang JPMS, phải thiết kế `requires`, `exports`, `opens` và thử việc tiêu thụ thực tế.
6. **Có bằng chứng hồi quy không?** Unit/integration/compatibility tests, quan sát triển khai thử và khả năng quay lại khi gặp lỗi.

Không gộp tất cả thay đổi lớn thành một đợt refactor khó đánh giá. Nên tách **nâng runtime/toolchain**, **đổi hợp đồng API** và **tái cấu trúc nội bộ** thành các bước có bằng chứng rõ khi thực tế cho phép.

### Trường hợp: một thư viện cũ cần tương thích, ứng dụng mới muốn dùng tính năng mới

Có thể giữ thư viện lõi ở mức Java 11, còn ứng dụng dùng Java 17 sử dụng `record` cho DTO riêng và chuyển đổi sang hợp đồng thư viện ở adapter. Đây là một quyết định ranh giới có đánh đổi: thêm một bước ánh xạ nhưng bảo toàn nhóm người dùng Java 11.

Ngược lại, nếu mọi bên tiêu thụ cùng chuyển sang Java 17 và chấp nhận thay đổi public API, việc cập nhật toàn bộ thư viện có thể hợp lý. **Điều kiện quyết định không phải “Java 17 hiện đại hơn”**, mà là hợp đồng và vòng đời của từng artifact.

## 12. Những sai lầm thường gặp

**“Máy phát triển có JDK 21, nên mọi module đều dùng được tính năng Java 21.”** Sai: module có thể công bố target 11/17; còn phụ thuộc vào cấu hình build và runtime nơi deploy.

**“Dùng `record` giúp mọi lớp dữ liệu trở thành bất biến sâu.”** Sai: các thành phần tham chiếu đến collection hoặc đối tượng mutable vẫn có thể đổi bên trong; cần hợp đồng và sao chép phòng vệ khi phù hợp.

**“Gradle subproject nào cũng phải có `module-info.java`.”** Sai: build module và JPMS named module là hai khái niệm khác nhau; có thể phối hợp nhưng không đồng nhất.

**“Package tên `internal` tự bảo đảm không ai dùng được.”** Sai: tên package diễn đạt ý định, không phải cơ chế kiểm soát quyền truy cập trên classpath. JPMS trên module path có cơ chế export phù hợp, nhưng vẫn cần thiết kế và cấu hình đúng.

**“Thư viện và adapter đều nên cấm mọi phụ thuộc framework.”** Không hợp lý: adapter thường được tạo để chứa những chi tiết framework; ranh giới cần tránh là để chúng tràn vào phần lõi không cần biết.

**“Bật mọi preview feature để code ngắn nhất.”** Có thể tạo khó khăn tương thích và bảo trì, nhất là với public API hoặc nhiều runtime khác nhau.

**“Đã format và lint xanh nghĩa là module thiết kế đúng.”** Công cụ kiểm tra hình thức và một số mẫu lỗi; nó không xác nhận đúng chiều phụ thuộc, đúng hợp đồng nghiệp vụ hay bảo đảm chạy được trên mọi môi trường.

**“Nâng JDK thì chỉ cần thay cú pháp cho hiện đại.”** Có thể vô tình thay public API, binary compatibility hoặc mô hình serialization. Cần xác định phạm vi và kiểm thử tương thích.

**“Càng nhiều ngoại lệ style càng linh hoạt.”** Ngoại lệ không rõ lý do khiến người bảo trì phải học nhiều chuẩn ngầm; nên ghi phạm vi, chủ sở hữu và điều kiện bỏ ngoại lệ.

## 13. Checklist khi review quy ước trong một mô-đun

Khi xem một thay đổi Java, hãy trả lời:

1. **Module phải chạy trên Java nào?** Ngôn ngữ, API chuẩn, compiler release, dependency và runtime đã thống nhất chưa?
2. **Đang nói đến loại module nào?** Build subproject, JPMS named module, library API, application, adapter hay test?
3. **Tính năng ngôn ngữ được dùng có hợp lệ và phù hợp với ý nghĩa không?** Dùng record để biểu diễn giá trị hay chỉ vì giảm số dòng?
4. **Ai là bên dùng hợp đồng?** Public API cần giữ tương thích ở mức nào; có làm lộ kiểu/framework nội bộ không?
5. **Ranh giới đóng gói có được áp dụng trong môi trường chạy thật không?** Nếu dùng JPMS, package export và reflection có được xử lý đúng?
6. **Quy ước chung và ngoại lệ có được ghi rõ?** Người mới mở module có thể biết luật nào áp dụng không?
7. **Có bằng chứng kiểm chứng chưa?** Compiler/build theo target, unit test và kiểm thử tiêu thụ artifact ở runtime/module path tương ứng?
8. **Chi phí thay đổi có hợp lý không?** Có áp đặt lớp trừu tượng, cú pháp mới hay cơ chế module mà bài toán chưa cần không?

Nếu một nguyên tắc đúng với **mọi thành phần**, đưa vào quy tắc chung và tự động hóa nơi có thể. Nếu nó chỉ đúng cho **một loại module hoặc một mức Java**, hãy ghi chính xác phạm vi. Đây là nền tảng của sự nhất quán bền vững.

## 14. Bài tập áp dụng

Giả sử repository có ba phần:

- **`legacy-payments-api`:** thư viện được nhiều ứng dụng Java 11 sử dụng; công bố các lớp đầu vào và kết quả thanh toán.
- **`shop-app`:** ứng dụng đang chạy Java 17, cần gọi thư viện thanh toán và xuất dữ liệu JSON.
- **`shop-app-tests`:** bộ kiểm thử dùng JUnit 5 và có thể dựng dữ liệu giả.

Một người đề xuất:

> “Để nhất quán, chuyển tất cả DTO của ba phần thành record, thêm `module-info.java` cho từng subproject và cho phép các lớp application gọi trực tiếp package `internal` của library.”

Hãy phân tích:

1. Phần nào **không thể** chuyển sang `record` nếu vẫn giữ target Java 11?
2. Phần nào có thể dùng record cho dữ liệu mới mà không buộc public API cũ phải đổi?
3. Vì sao thêm `module-info.java` cho mọi build subproject chưa chắc đúng? Phải kiểm tra gì nếu thật sự dùng JPMS?
4. Có nên cho ứng dụng phụ thuộc trực tiếp package `internal` của library không? Nếu thiếu năng lực trong public API, xử lý thế nào?
5. Những test nào cần chạy để xác minh phiên bản, hành vi thanh toán và việc tiêu thụ artifact?

**Gợi ý:** Thư viện còn cam kết Java 11 không thể dùng record trong mã Java 11; ứng dụng Java 17 có thể dùng record cho DTO riêng và ánh xạ sang API thư viện. JPMS cần được quyết định theo mô hình phát hành và chạy thực tế, không suy ra từ số subproject. Ứng dụng nên dùng contract công khai; nếu contract thiếu, cần mở rộng theo chính sách tương thích thay vì chui vào nội bộ. Cần build theo target, kiểm tra dependency, chạy test hợp đồng và thử ứng dụng tiêu thụ trên runtime thật.

## 15. Ghi nhớ

**Quy tắc nhất quán phải phù hợp với phiên bản Java và trách nhiệm của từng mô-đun.** Java 11, 17 và 21 có khả năng cú pháp/API khác nhau; library, application, adapter và test có các hợp đồng và giới hạn khác nhau; build subproject không tự đồng nghĩa JPMS named module. Hãy có **nguyên tắc chung**, công bố **ngoại lệ theo phạm vi**, kiểm tra được mức tương thích và bảo vệ ranh giới công khai bằng kiểm thử. Khi quy ước phản ánh đúng bối cảnh, mã nguồn trở nên **dễ hiểu, đáng tin cậy và dễ thay đổi hơn mà không đánh mất khả năng tương thích cần thiết**.
