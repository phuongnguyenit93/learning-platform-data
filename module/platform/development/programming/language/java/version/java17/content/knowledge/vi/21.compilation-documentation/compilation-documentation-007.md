# @since, --since và --since-label trong tài liệu API

Tag `@since` ghi phiên bản release mà một API được giới thiệu. Javadoc hiển thị tag này trong phần Since của trang tài liệu.

Ở cấp công cụ, Javadoc mới hơn có thêm các tùy chọn --since và --since-label để tạo trang tổng hợp API mới. Hai tùy chọn này cần được phân biệt với tag @since.

## 1. Tag @since là gì?

**@since** là block tag trong documentation comment, dùng để ghi phiên bản phần tử API đã có từ đó. Javadoc hiển thị nội dung của tag dưới heading **Since** trong trang tài liệu được sinh ra.

~~~java
/**
 * Represents a request accepted by the service.
 *
 * @since 17
 */
public final class ServiceRequest {
}
~~~

Tag có thể xuất hiện trong documentation comment của module, package, class, interface, constructor, method, field và trang overview. Tag này đã được hỗ trợ từ JDK 1.1.

### 1.1. Cú pháp và ý nghĩa

~~~text
@since since-text
~~~

**since-text** là văn bản mô tả phiên bản. Javadoc không phân tích nội dung này thành một cấu trúc phiên bản có quy tắc số học; nó được hiển thị như văn bản.

~~~java
/**
 * Returns the normalized identifier.
 *
 * @return normalized identifier
 * @since 17
 */
public String normalizedId() {
    return id.trim().toLowerCase(Locale.ROOT);
}
~~~

Với Java platform API, giá trị **@since** biểu thị phiên bản của đặc tả API Java mà phần tử được đưa vào. Nó không nhất thiết là thời điểm source code được thêm vào repository của bản triển khai tham chiếu. Với thư viện riêng, nhóm phát triển thường dùng số phiên bản đầu tiên mà API được công bố, theo quy ước versioning của thư viện.

## 2. Đặt @since ở đâu?

Hãy ghi **@since** tại nơi người đọc cần biết mốc ra đời của API.

### 2.1. API mới trong class đã tồn tại

Giả sử class được giới thiệu từ Java 11, nhưng một method chỉ được thêm ở release 17:

~~~java
/**
 * Provides information about a service.
 *
 * @since 11
 */
public class ServiceInfo {
    /**
     * Returns the service name.
     */
    public String name() {
        return name;
    }

    /**
     * Returns the service health state.
     *
     * @since 17
     */
    public Health health() {
        return health;
    }
}
~~~

Class có mốc **11**, còn method **health()** có mốc **17**. Nếu member xuất hiện muộn hơn class, hãy ghi tag riêng cho member đó.

### 2.2. Package, module, field và constructor

Package comment:

~~~java
/**
 * Public API for service monitoring.
 *
 * @since 17
 */
package com.example.monitoring;
~~~

Module comment:

~~~java
/**
 * Provides service monitoring APIs.
 *
 * @since 17
 */
module com.example.monitoring {
    exports com.example.monitoring;
}
~~~

Field và constructor cũng có thể có tag riêng:

~~~java
public final class RetryPolicy {
    /**
     * Default maximum number of attempts.
     *
     * @since 17
     */
    public static final int DEFAULT_ATTEMPTS = 3;

    /**
     * Creates a policy with the given attempt limit.
     *
     * @param attempts maximum number of attempts
     * @since 17
     */
    public RetryPolicy(int attempts) {
        this.attempts = attempts;
    }
}
~~~

## 3. Phân biệt @since, @version và @Deprecated(since)

Ba thông tin này có liên quan tới version nhưng trả lời các câu hỏi khác nhau:

| Thành phần | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| **@since 17** | API đã có từ release nào? | Method được giới thiệu trong Java SE 17 |
| **@version 2.4** | Tài liệu hoặc thành phần phần mềm đang mô tả version nào? | Phiên bản hiện tại của thư viện |
| **@Deprecated(since = "18")** | API bị đánh dấu deprecated từ release nào? | API bắt đầu deprecated từ Java 18 |

**@since** không có nghĩa là API vẫn còn được khuyến nghị. Một method có thể được giới thiệu ở Java 11 rồi bị deprecated ở Java 17.

~~~java
/**
 * Sends a request using the old transport.
 *
 * @deprecated Use {@link #sendWithClient(Request)} instead.
 * @since 11
 */
@Deprecated(since = "17", forRemoval = false)
public Response send(Request request) {
    // ...
}
~~~

Trong ví dụ, **@since 11** nói method được giới thiệu ở release 11; **@Deprecated(since = "17")** nói method bị deprecated ở release 17; **@deprecated** giải thích trạng thái deprecated và hướng người dùng tới API thay thế. Tag @deprecated và annotation @Deprecated nên được dùng cùng nhau để nội dung tài liệu và metadata của compiler nhất quán.

## 4. Javadoc hiển thị @since như thế nào?

Khi chạy standard doclet, mỗi tag **@since** được trình bày thành một mục **Since** trong trang API tương ứng. Tag không tự tạo một trang tổng hợp tất cả API mới của release.

~~~java
/**
 * Returns the current status.
 *
 * @since 17
 */
public Status status() {
    // ...
}
~~~

Javadoc có tùy chọn **-nosince** để bỏ các mục Since khỏi tài liệu sinh ra:

~~~bash
javadoc -nosince -d docs com.example.api
~~~

Tùy chọn này chỉ ảnh hưởng cách hiển thị các phần Since trong output. Nó không xóa tag khỏi source code và cũng không thay đổi lịch sử API trong source. Thông thường, tài liệu API công khai nên giữ thông tin Since vì nó giúp người dùng kiểm tra khả năng tương thích giữa các phiên bản.

## 5. --since và --since-label xuất hiện từ JDK 18

Điểm phiên bản quan trọng đối với chủ đề này:

| Javadoc tool | @since | --since | --since-label |
| --- | --- | --- | --- |
| JDK 17 | Có | Không hỗ trợ | Không hỗ trợ |
| JDK 18 trở lên | Có | Có | Có |

Javadoc JDK 17 có tag **@since** và tùy chọn **-nosince**, nhưng command reference của JDK 17 không liệt kê **--since** hoặc **--since-label**. Hai tùy chọn này có trong tài liệu công cụ từ JDK 18.

Vì vậy, nếu chạy:

~~~bash
javadoc --since 17 --since-label "New API in Java SE 17" ...
~~~

bằng executable **javadoc** của JDK 17, công cụ sẽ báo tùy chọn không hợp lệ. Muốn dùng hai option này, hãy chạy Javadoc tool từ JDK 18 trở lên.

**Phiên bản của Javadoc executable quyết định option được hỗ trợ.** Việc source code hướng tới Java 17 hoặc dùng **--release 17** không bổ sung những option mà executable JDK 17 chưa có.

## 6. --since dùng để làm gì?

**--since** yêu cầu standard doclet tạo trang tổng hợp các API được thêm mới hoặc mới bị deprecated trong các release được chỉ định.

Cú pháp:

~~~text
--since release[,release]*
~~~

Ví dụ:

~~~bash
javadoc --since 17 -d docs com.example.api
~~~

Nếu documentation comment của một phần tử có tag **@since** khớp chính xác release được chỉ định, Javadoc đưa thông tin về phần tử đó và release giới thiệu nó vào trang **New API**.

Tùy chọn cũng dùng metadata của annotation **java.lang.Deprecated**: nếu trang Deprecated API được tạo và giá trị **since** của annotation khớp release được chỉ định, thông tin release mà phần tử bị deprecated được thêm vào trang Deprecated API.

### 6.1. Giá trị release được so sánh như thế nào?

Javadoc so sánh release dưới dạng chuỗi, phân biệt chữ hoa/chữ thường. Đây không phải phép so sánh số phiên bản:

| Giá trị trong source | Giá trị truyền vào --since | Khớp? |
| --- | --- | --- |
| @since 17 | --since 17 | Có |
| @since 17 | --since 17,18 | Có |
| @since 17 | --since 17.0 | Không |
| @since 17 | --since Java 17 | Không |
| @since 17 | --since 17-ea | Không |

Hãy thống nhất quy ước version string trong source và command build. Với Java platform release, dùng giá trị ngắn gọn như **17**, **18**. Với thư viện riêng, chọn quy ước rõ ràng, ví dụ **2.4**, rồi dùng đúng chuỗi đó trong lệnh.

### 6.2. Nhiều release trong một lần chạy

Có thể yêu cầu nhiều release bằng cách phân tách bằng dấu phẩy:

~~~bash
javadoc --since 17,18,21 -d docs com.example.api
~~~

Javadoc tổng hợp các API có tag hoặc metadata deprecated khớp các release đã chọn. Dấu phẩy là dấu phân cách trong cùng một đối số; không viết mỗi release thành một đối số riêng sau option.

## 7. --since-label dùng để làm gì?

**--since-label** chỉ định nội dung heading trên trang **New API** được tạo bởi **--since**. Nó tùy chỉnh nhãn hiển thị, không thay đổi điều kiện lọc release.

Cú pháp:

~~~text
--since-label text
~~~

Ví dụ:

~~~bash
javadoc --since 17 --since-label "API mới trong Java SE 17" -d docs com.example.api
~~~

Nhãn có thể mô tả release hoặc phạm vi tài liệu:

~~~bash
javadoc --since 17,18 --since-label "New API in releases 17 and 18" -d docs com.example.api
~~~

**--since-label** chỉ đổi heading. Nó không thay đổi giá trị @since trong source, tập release được chọn, cách so sánh chuỗi, các mục Since trên từng trang class/member hoặc metadata @Deprecated(since = ...).

Nếu không cần heading riêng, có thể bỏ **--since-label** và dùng nhãn mặc định của standard doclet.

## 8. Ví dụ đầy đủ: đánh dấu API và tạo trang New API

Giả sử thư viện có class tồn tại từ release 11 và method mới được bổ sung ở release 17:

~~~java
package com.example.api;

/**
 * Provides information about a service.
 *
 * @since 11
 */
public final class ServiceInfo {
    /**
     * Returns the service name.
     *
     * @return service name
     */
    public String name() {
        return "orders";
    }

    /**
     * Returns the current health state.
     *
     * @return health state
     * @since 17
     */
    public Health health() {
        return Health.UP;
    }
}
~~~

Enum được bổ sung cùng release:

~~~java
package com.example.api;

/**
 * Health state of a service.
 *
 * @since 17
 */
public enum Health {
    UP,
    DEGRADED,
    DOWN
}
~~~

Có thể tạo tài liệu bằng JDK 17:

~~~bash
javadoc --release 17 -d docs src/main/java/com/example/api/*.java
~~~

Kết quả có các trang API và phần Since theo tag. JDK 17 không có trang tổng hợp New API được tạo bằng **--since**.

Nếu dùng JDK 18 trở lên để chạy Javadoc nhưng vẫn muốn tài liệu mô tả API theo Java 17:

~~~bash
javadoc --release 17 --since 17 --since-label "New API in Java SE 17" -d docs src/main/java/com/example/api/*.java
~~~

Ở đây:

- JDK 18+ cung cấp executable có hỗ trợ **--since** và **--since-label**.
- **--release 17** yêu cầu Javadoc dùng mô hình API/platform của Java 17 khi xử lý source.
- **@since 17** trong comment cung cấp dữ liệu để trang New API nhận diện phần tử được thêm trong release 17.

Không nhầm **--release 17** với **--since 17**: option đầu xác định release nền tảng Java dùng để biên dịch/phân tích; option sau chọn mốc API để tạo trang tổng hợp.

## 9. Kết hợp @since với @Deprecated(since)

Từ Java 9, annotation **@Deprecated** có phần tử **since** và **forRemoval**:

~~~java
@Deprecated(since = "17", forRemoval = false)
~~~

- **since** cho biết release mà phần tử được đánh dấu deprecated.
- **forRemoval = false** cho biết API đang bị discourage nhưng tại thời điểm đánh dấu chưa có ý định loại bỏ cụ thể.
- **forRemoval = true** cho biết API được dự kiến loại bỏ trong tương lai.

Để Javadoc giải thích lý do và API thay thế, nên thêm tag **@deprecated**:

~~~java
/**
 * Opens a legacy connection.
 *
 * @deprecated Use {@link #openClient()} instead.
 * @since 11
 */
@Deprecated(since = "17", forRemoval = false)
public Connection openConnection() {
    // ...
}
~~~

Khi chạy Javadoc tool có hỗ trợ **--since 17**, thông tin deprecated release có thể được đưa vào trang Deprecated API nếu trang này được tạo và annotation có giá trị khớp. **@since 11** vẫn mô tả thời điểm API ban đầu được giới thiệu.

Không đổi **@since** thành release deprecated. Hai mốc này có ý nghĩa khác nhau và cần được giữ riêng.

## 10. Quy ước ghi release string cho dự án

Để **--since** hoạt động ổn định, nhóm phát triển nên có quy ước thống nhất:

1. Dùng một release token đơn giản cho mỗi lần giới thiệu API, ví dụ **17** hoặc **2.4**.
2. Giữ nguyên cách viết trong source, build script và tài liệu phát hành.
3. Tránh thêm tiền tố hoặc hậu tố mô tả như **Java 17**, **v2.4 release** vào tag nếu muốn so khớp bằng **--since**.
4. Ghi tag trên class/package/module khi cả nhóm API được giới thiệu cùng lúc.
5. Ghi tag riêng trên member nếu member được bổ sung ở release khác.
6. Khi deprecated, cập nhật annotation **@Deprecated(since = ...)** và viết mô tả **@deprecated**.
7. Không sửa mốc **@since** cũ chỉ vì version hiện tại đã tăng; đó là lịch sử API.

### 10.1. Không dùng @since như changelog

**@since** không phải danh sách mọi thay đổi của một API. Nếu method đã có từ release 11 nhưng được sửa implementation ở release 17, mốc **@since** vẫn là 11.

Các thông tin như bug fix, thay đổi hành vi, giới hạn mới hoặc ghi chú migration nên nằm trong release notes, migration guide hoặc phần mô tả API phù hợp. Chỉ cập nhật **@since** khi phần tử API thực sự được giới thiệu trong release mới.

### 10.2. Không gắn tag theo ngày build

Không nên dùng ngày build, số CI hoặc patch build làm **@since** nếu người dùng cần biết phiên bản API. Mốc này phải theo release/versioning contract mà thư viện công bố.

## 11. Giới hạn và những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| JDK 17 hỗ trợ --since vì nó hỗ trợ @since | Không. JDK 17 hỗ trợ tag; hai option command-line xuất hiện từ JDK 18. |
| --since 17 lọc toàn bộ tài liệu chỉ còn API Java 17 | Nó tạo trang tổng hợp New API cho release được chọn; không có nghĩa mọi trang API khác bị loại khỏi output. |
| --since so sánh version theo thứ tự số | Không. Giá trị release được so sánh như chuỗi, có phân biệt chữ hoa/chữ thường. |
| --since-label thay đổi tag @since | Không. Nó chỉ thay heading của trang New API. |
| @since ghi thời điểm source code được commit | Với Java platform API, tag mô tả phiên bản đặc tả API; với thư viện riêng, nó theo quy ước release của thư viện. |
| @since và @Deprecated(since) là cùng một mốc | Không. Một mốc giới thiệu API; mốc kia ghi release deprecated. |
| @since tự tạo trang New API | Không. Tag tạo mục Since trên trang phần tử; trang tổng hợp cần Javadoc tool hỗ trợ --since. |
| Chạy javadoc --release 17 sẽ có option của JDK 18 | Không. --release không nâng phiên bản executable. |
| --since-label dùng để lọc release | Không. Nó chỉ tùy chỉnh tiêu đề hiển thị. |

## 12. Câu hỏi tự kiểm tra

**1. Tag @since dùng để ghi điều gì?**  
Phiên bản release mà API hoặc phần tử được giới thiệu.

**2. @since có dùng được với Javadoc JDK 17 không?**  
Có. Đây là tag chuẩn đã có từ JDK 1.1.

**3. @since hợp lệ ở những loại documentation comment nào?**  
Overview, module, package, class, interface, constructor, method và field.

**4. @since có tự tạo trang New API không?**  
Không. Nó hiển thị mục Since trên trang phần tử; trang tổng hợp cần option --since của Javadoc tool mới hơn.

**5. JDK 17 có hỗ trợ --since và --since-label không?**  
Không. Hai option này có từ JDK 18.

**6. --since tạo ra loại thông tin nào?**  
Trang New API tổng hợp các API được thêm ở release được chỉ định và thông tin release deprecated tương ứng nếu có.

**7. --since nhận nhiều release như thế nào?**  
Dùng một đối số phân tách bằng dấu phẩy, ví dụ --since 17,18,21.

**8. Giá trị @since 17 có khớp với --since 17.0 không?**  
Không. Javadoc so sánh chuỗi release chính xác, không phân tích số phiên bản.

**9. --since-label thay đổi điều gì?**  
Nội dung heading của trang New API; nó không thay đổi dữ liệu release hoặc điều kiện lọc.

**10. Khác biệt giữa @since và @Deprecated(since = ...) là gì?**  
@since ghi release giới thiệu API; @Deprecated(since = ...) ghi release API bị deprecated.

**11. Nếu dùng Javadoc JDK 18 để sinh tài liệu cho API Java 17, có thể dùng --release 17 cùng --since 17 không?**  
Có. JDK 18 tool cung cấp option; --release 17 chọn nền tảng API Java 17.

**12. Có nên thay @since 11 thành @since 17 khi nâng phiên bản thư viện lên 17 không?**  
Không, trừ khi API thực sự được giới thiệu ở release 17. Mốc @since là lịch sử giới thiệu, không phải version hiện tại.

## Tài liệu tham khảo chính thức

- [Java SE 17 — Documentation Comment Specification, @since](https://docs.oracle.com/en/java/javase/17/docs/specs/javadoc/doc-comment-spec.html): cú pháp, vị trí hợp lệ và ý nghĩa của tag @since.
- [Java SE 17 — The javadoc Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javadoc.html): các tùy chọn Javadoc có trong JDK 17; có -nosince nhưng không có --since hoặc --since-label.
- [Java SE 18 — The javadoc Command](https://docs.oracle.com/en/java/javase/18/docs/specs/man/javadoc.html): tài liệu định nghĩa --since và --since-label, bao gồm cách so khớp release.
- [Java SE 17 API — Deprecated](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Deprecated.html): phần tử since và forRemoval của annotation @Deprecated.
