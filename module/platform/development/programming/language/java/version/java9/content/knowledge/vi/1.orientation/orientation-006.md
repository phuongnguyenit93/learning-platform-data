# Tra cứu hợp đồng API, mốc xuất hiện và tình trạng hỗ trợ

## Mục tiêu

Khi sử dụng Java, chỉ biết tên class hoặc method là chưa đủ. Cần xác định API đó được công bố trong phiên bản nào, cam kết hành vi của nó là gì, có đang bị deprecated hay không, có phải preview/incubator/internal API không và phiên bản JDK chứa API đó còn được nhà cung cấp hỗ trợ hay không.

Bài này hướng dẫn một quy trình tra cứu có thể lặp lại bằng tài liệu API chính thức, Javadoc, JEP và các công cụ JDK. Trọng tâm là phân biệt **hợp đồng API**, **lịch sử phiên bản của API** và **vòng đời hỗ trợ của bản JDK**. Ba thông tin này liên quan nhưng không thay thế cho nhau.

Sau bài này, bạn có thể:

- Tìm đúng tài liệu API theo phiên bản Java mục tiêu.
- Đọc hợp đồng của class, method, constructor và package.
- Xác định mốc xuất hiện qua `@since` và lịch sử JEP.
- Diễn giải `@Deprecated`, `since` và `forRemoval`.
- Phân biệt API chuẩn, preview, incubator, internal và API đã bị loại bỏ.
- Kiểm tra khả năng tương thích bằng `javac --release`, `jdeprscan` và `jdeps`.
- Tra cứu chính xác tình trạng hỗ trợ của JDK theo nhà cung cấp.

## 1. Ba câu hỏi phải trả lời khi tra cứu một API

Khi gặp một API như `java.net.http.HttpClient`, hãy tách việc tra cứu thành ba câu hỏi.

### 1.1. Hợp đồng API quy định điều gì?

Hợp đồng API (API contract) là phần mô tả chính thức về cách chương trình được phép sử dụng API và hành vi mà API cam kết. Nó có thể bao gồm:

- Tên class/interface, package, module và modifier.
- Constructor, method, field, kiểu generic và kiểu trả về.
- Ý nghĩa tham số, giá trị trả về và ngoại lệ được khai báo.
- Điều kiện đầu vào, giới hạn và hành vi khi tham số không hợp lệ.
- Quy tắc về null, thứ tự phần tử, khả năng sửa đổi và vòng đời đối tượng.
- Hành vi đồng bộ/bất đồng bộ, blocking, thread-safety và trạng thái chia sẻ nếu tài liệu quy định.
- Tác dụng phụ, quyền truy cập, bảo mật và các giới hạn vận hành.

Ví dụ, chỉ biết `List.of(...)` tạo một List là chưa đủ. Hợp đồng còn quy định danh sách trả về không thể sửa đổi và không chấp nhận phần tử null. Nếu code cố gọi `add` hoặc truyền null, chương trình sẽ gặp hành vi đã được API tài liệu hóa, không phải một chi tiết tùy ý của implementation.

Không suy luận hợp đồng từ tên method, cách implementation đang chạy trên một JDK cụ thể hoặc một bài viết không chính thức. Tài liệu API của đúng phiên bản là nguồn chính để xác định cam kết công khai.

### 1.2. API xuất hiện từ phiên bản nào?

Mốc xuất hiện thường được ghi bằng Javadoc tag `@since`. Trong trang Javadoc đã sinh, thông tin này thường hiển thị dưới mục **Since**.

Ví dụ:

- `java.util.List.of` được giới thiệu trong Java 9.
- `java.net.http.HttpClient` là API chuẩn từ Java 11.
- Một API của thư viện bên thứ ba có thể dùng số phiên bản riêng, không nhất thiết trùng số phiên bản JDK.

Mốc `@since` cho biết API được tài liệu hóa từ phiên bản nào. Nó không tự cho biết API có còn được hỗ trợ, có bị deprecated hay có được nhà cung cấp duy trì hay không.

### 1.3. API và JDK hiện có tình trạng hỗ trợ nào?

Phải xác định riêng:

- API đang là API chuẩn, deprecated, preview, incubator, internal hay đã bị loại bỏ?
- Bản JDK đang dùng thuộc dòng phát hành nào và nhà cung cấp nào?
- Nhà cung cấp còn cập nhật bảo mật, sửa lỗi và hỗ trợ kỹ thuật cho bản JDK đó đến khi nào?
- Ứng dụng có phụ thuộc vào API chỉ tồn tại trong một JDK hoặc một bản phân phối cụ thể không?

Một API có thể vẫn là API chuẩn dù phiên bản JDK cũ chứa nó đã hết thời hạn hỗ trợ. Ngược lại, một JDK còn được nhà cung cấp hỗ trợ không làm cho API internal hoặc incubator tự trở thành API ổn định.

## 2. Tìm đúng tài liệu API chính thức

### 2.1. Chọn đúng phiên bản tài liệu

Javadoc của Java SE được phát hành theo từng phiên bản. Khi kiểm tra tương thích, hãy mở tài liệu của **phiên bản mục tiêu**, không chỉ mở trang mới nhất.

Ví dụ:

| Mục đích | Tài liệu nên dùng |
|---|---|
| Kiểm tra ứng dụng phải chạy trên Java 17 | Java SE 17 API Specification |
| Kiểm tra ứng dụng phải chạy trên Java 21 | Java SE 21 API Specification |
| Xem API mới nhất của nền tảng Java SE 26 | Java SE 26 API Specification |
| Xem module và package thuộc JDK | Trang module/package trong Javadoc của đúng bản JDK |

Trang API tổng thể của Java SE 26:

https://docs.oracle.com/en/java/javase/26/docs/api/

Các bản tài liệu khác có cùng cấu trúc URL theo số phiên bản, ví dụ:

- https://docs.oracle.com/en/java/javase/17/docs/api/
- https://docs.oracle.com/en/java/javase/21/docs/api/
- https://docs.oracle.com/en/java/javase/25/docs/api/

Nếu ứng dụng phải tương thích Java 17, việc một method xuất hiện trong tài liệu Java 26 không có nghĩa ứng dụng có thể gọi method đó khi chạy trên Java 17.

### 2.2. Tìm từ package đến method

Một quy trình tra cứu thực tế:

1. Tìm tên đầy đủ của class/interface, ví dụ `java.net.http.HttpClient`.
2. Mở trang API của class trong đúng phiên bản JDK.
3. Xác định module và package chứa class.
4. Đọc phần mô tả tổng quan trước khi xem từng method.
5. Tìm method cần dùng trong phần Method Summary và Method Details.
6. Kiểm tra tham số, kết quả, ngoại lệ, ghi chú và mốc Since.
7. Đọc phần See Also, superclass/interface và các API liên quan.

Với Java modular, cần chú ý cả module sở hữu package. Ví dụ `java.net.http` là module chứa package `java.net.http`; khi viết named module, ứng dụng cần khai báo dependency thích hợp:

~~~java
module com.example.client {
    requires java.net.http;
}
~~~

Tên package và tên module có thể giống hoặc khác nhau. Đừng suy ra tên module chỉ từ package.

### 2.3. Đọc Method Details thay vì chỉ nhìn Method Summary

Method Summary hữu ích để tìm nhanh tên và chữ ký. Method Details mới cung cấp phần giải thích hành vi quan trọng.

Ví dụ khi đọc một method gửi HTTP request, cần kiểm tra:

- Request phải được tạo như thế nào?
- Method có blocking hay trả về một `CompletableFuture`?
- Những trạng thái lỗi nào được biểu diễn bằng exception?
- Response body được xử lý theo kiểu nào?
- Có yêu cầu về executor, timeout hoặc client lifecycle không?

Nếu Javadoc ghi rõ một điều kiện, hãy xem đó là phần hợp đồng. Nếu tài liệu không nói đến một hành vi, không tự biến hành vi quan sát được trên một implementation thành cam kết chung.

## 3. Xác định mốc xuất hiện bằng `@since`

### 3.1. Javadoc tag `@since`

`@since` là Javadoc tag mô tả phiên bản mà API hoặc phần tử tài liệu được đưa vào. Ví dụ:

~~~java
/**
 * Creates an unmodifiable list containing the supplied elements.
 *
 * @since 9
 */
static <E> List<E> of(E e1, E e2) {
    // API declaration shown for explanation
}
~~~

Đây là ví dụ minh họa cách ghi Javadoc; không phải mã nguồn triển khai thật của JDK.

Trong Javadoc được sinh, tag này thường tạo mục **Since**. Hãy kiểm tra ở cấp phần tử cụ thể vì một class có thể đã tồn tại từ lâu nhưng một method overload hoặc constant mới được bổ sung ở phiên bản sau.

Không chỉ xem `@since` ở class. Cần tra đúng constructor, method, field hoặc nested type đang sử dụng.

### 3.2. Không nhầm `@since` với phiên bản đang được hỗ trợ

Ví dụ, nếu method có `@since 9`, điều đó có nghĩa method đã xuất hiện từ Java 9. Nó không có nghĩa:

- Java 9 vẫn còn được hỗ trợ.
- Method chỉ chạy trên Java 9.
- Method đã bị deprecated.
- Method chắc chắn còn tồn tại trong mọi JDK tương lai.
- Mọi nhà cung cấp đều hỗ trợ cùng một thời hạn.

Một method từ Java 9 có thể tiếp tục là API chuẩn trên Java 26. Mốc xuất hiện và tình trạng hiện tại phải được tra ở hai nơi khác nhau.

### 3.3. Khi thiếu `@since`

Một số API hoặc thư viện không ghi đầy đủ tag `@since`. Khi đó:

- Kiểm tra tài liệu phát hành của thư viện hoặc JDK.
- Kiểm tra release notes và lịch sử thay đổi chính thức.
- Tìm JEP nếu thay đổi thuộc một tính năng được đặc tả qua JEP.
- So sánh Javadoc của các phiên bản liền kề.
- Kiểm tra source tag hoặc lịch sử repository chính thức nếu dự án công khai mã nguồn.

Không tự gán mốc phiên bản dựa trên ngày của một bài blog hoặc ngày phát hành của một artifact có tên tương tự.

## 4. Dùng JEP và release notes để hiểu lịch sử API

JEP (JDK Enhancement Proposal) mô tả đề xuất, mục tiêu, phạm vi và tiến trình của một thay đổi trong JDK. JEP hữu ích để tìm hiểu vì sao API xuất hiện, thay đổi qua các bản preview/incubator như thế nào và quyết định chuẩn hóa được thực hiện ở đâu.

Tuy nhiên, JEP không thay thế hợp đồng API. Khi code dựa vào một method cụ thể, vẫn phải đọc Javadoc của method trong phiên bản Java mục tiêu.

### Ví dụ: HTTP Client

HTTP Client là ví dụ tốt về một tính năng trải qua giai đoạn incubator trước khi trở thành API chuẩn:

| Mốc | Tình trạng | Ý nghĩa |
|---|---|---|
| Java 9 | Incubator, module `jdk.incubator.httpclient` | API thử nghiệm được cung cấp để thu thập phản hồi và tiếp tục hoàn thiện |
| Java 10 | Tiếp tục incubator | API vẫn có thể thay đổi trước khi chuẩn hóa |
| Java 11 | API chuẩn trong module `java.net.http` | HTTP Client được chuẩn hóa thành API Java SE |

Các tài liệu lịch sử chính:

- JEP 110 — HTTP/2 Client (Incubator): https://openjdk.org/jeps/110
- JEP 321 — HTTP Client (Standard): https://openjdk.org/jeps/321

Khi tra cứu một API lịch sử, đừng chỉ tìm tên class. Hãy tìm cả module/package của từng giai đoạn. Tên package và module có thể thay đổi khi API chuyển từ incubator sang chuẩn hóa.

Với ứng dụng mới, hãy dùng API chuẩn hiện hành `java.net.http.HttpClient` và tài liệu của Java SE mục tiêu. Chỉ đọc API incubator cũ khi cần duy trì hoặc di trú một ứng dụng Java 9/10 đã tồn tại.

## 5. Diễn giải trạng thái deprecated

### 5.1. Javadoc `@deprecated` và annotation `@Deprecated`

Hai dạng này có liên quan nhưng vai trò khác nhau:

- Javadoc tag `@deprecated` nằm trong comment và giải thích vì sao API không còn được khuyến nghị, đồng thời chỉ ra lựa chọn thay thế nếu có.
- Annotation `@Deprecated` gắn vào declaration để compiler, IDE và công cụ phân tích có thể nhận biết API deprecated.

Ví dụ:

~~~java
/**
 * Legacy entry point.
 *
 * @deprecated Use the replacement method instead.
 * @since 9
 */
@Deprecated(since = "9", forRemoval = false)
public void oldOperation() {
}
~~~

Đây là ví dụ minh họa trong code do ứng dụng định nghĩa.

### 5.2. Thuộc tính `since`

Từ Java 9, annotation `@Deprecated` có thuộc tính `since` để ghi phiên bản mà API được đánh dấu deprecated.

Ví dụ:

~~~java
@Deprecated(since = "9")
public void oldOperation() {
}
~~~

Giá trị `since` là metadata về mốc deprecated, không phải ngày kết thúc hỗ trợ và cũng không phải mốc API lần đầu xuất hiện.

### 5.3. Thuộc tính `forRemoval`

`forRemoval` cho biết API được dự kiến loại bỏ trong một bản phát hành tương lai:

~~~java
@Deprecated(since = "21", forRemoval = true)
public void oldOperation() {
}
~~~

Diễn giải:

- `forRemoval = false`: API đã deprecated nhưng không được đánh dấu rõ là dự kiến loại bỏ.
- `forRemoval = true`: API được đánh dấu là dự kiến loại bỏ trong tương lai.
- `forRemoval = true` không chỉ định chính xác phiên bản sẽ xóa API.
- Deprecated không đồng nghĩa với removed. API vẫn có thể tồn tại và chạy trong nhiều phiên bản sau khi bị deprecated.

Khi gặp API deprecated, hãy đọc phần `@deprecated` trong Javadoc để biết lý do và cách di trú. Đừng chỉ bỏ warning bằng `@SuppressWarnings("deprecation")` mà không đánh giá rủi ro.

### 5.4. Kiểm tra bằng reflection

Annotation `Deprecated` có thể được đọc ở runtime:

~~~java
Deprecated info =
    SomeClass.class.getDeclaredMethod("oldOperation")
        .getAnnotation(Deprecated.class);

if (info != null) {
    System.out.println("since=" + info.since());
    System.out.println("forRemoval=" + info.forRemoval());
}
~~~

Đoạn mã minh họa cách đọc metadata của một method. Nếu method không được gắn annotation, kết quả là null. Reflection chỉ đọc metadata; nó không cho biết ngày loại bỏ thực tế hoặc thời hạn hỗ trợ của JDK.

## 6. Phân biệt API chuẩn, preview, incubator và internal

Các trạng thái này ảnh hưởng trực tiếp đến độ ổn định của hợp đồng mà ứng dụng có thể dựa vào.

| Trạng thái | Ý nghĩa | Cách sử dụng |
|---|---|---|
| Standard API | API công khai thuộc Java SE hoặc một API được JDK công bố ổn định | Có thể dựa vào hợp đồng và quy tắc tương thích đã công bố |
| Preview feature | Tính năng được phát hành để thử nghiệm, có thể thay đổi hoặc bị loại bỏ | Phải bật preview đúng phiên bản và đánh giá rủi ro trước khi dùng |
| Incubator API/module | API đang được thử nghiệm trong module incubator | Chỉ dùng khi chấp nhận khả năng thay đổi và di trú |
| Internal API | API nội bộ của implementation JDK | Tránh phụ thuộc; không có cam kết ổn định như API công khai |
| Deprecated API | API không còn được khuyến nghị | Lập kế hoạch thay thế; kiểm tra `forRemoval` và hướng dẫn di trú |
| Removed API | API đã bị loại bỏ khỏi phiên bản đang tra cứu | Không thể biên dịch/chạy dựa vào API đó trên phiên bản này |

### Preview

Preview feature được phát hành để người dùng thử nghiệm trước khi quyết định hoàn thiện. Tài liệu Javadoc hoặc tài liệu tính năng sẽ đánh dấu trạng thái preview.

Khi biên dịch và chạy code dùng preview, phải bật `--enable-preview` cho đúng bản phát hành hỗ trợ tính năng đó. Không nên giả định code preview của một bản Java sẽ tự động hoạt động trên bản kế tiếp.

Ví dụ dạng lệnh tổng quát:

~~~bash
javac --release 26 --enable-preview -d out src/Main.java
java --enable-preview -cp out Main
~~~

Chỉ dùng lệnh này khi code thực sự dùng preview feature của đúng JDK 26. Ví dụ trên minh họa cấu trúc lệnh, không khẳng định một API cụ thể là preview trong Java 26.

### Incubator

Incubator API thường được đóng gói trong module có tên thể hiện trạng thái thử nghiệm, ví dụ `jdk.incubator.*`. Ứng dụng cần đưa module đó vào cấu hình khi biên dịch/chạy, thường bằng `--add-modules`.

Incubator có thể đổi package, chữ ký hoặc bị loại bỏ. Khi API được chuẩn hóa, hãy tra lại tên module/package và hợp đồng mới thay vì giữ nguyên code cũ.

### Internal API

Các package như `sun.*` hoặc `jdk.internal.*` thường thuộc implementation nội bộ của JDK. Chúng có thể bị đóng gói, thay đổi hoặc loại bỏ mà không tuân theo cam kết tương thích của API Java SE.

Không xem việc một class internal đang public hoặc có thể import được là bằng chứng nó được hỗ trợ. Dùng API công khai tương ứng nếu có.

## 7. Kiểm tra API có tồn tại và tương thích với phiên bản mục tiêu

### 7.1. Dùng `javac --release`

Khi code cần chạy trên Java 17, biên dịch bằng:

~~~bash
javac --release 17 -d out src/Main.java
~~~

`--release N` yêu cầu compiler kiểm tra theo ngôn ngữ, class-file target và tập API nền tảng công khai của release N. Đây là cách thực tế để phát hiện code vô tình gọi API chỉ xuất hiện ở phiên bản mới hơn.

Ví dụ, `List.of` có từ Java 9 nên phù hợp với `--release 9` trở lên. `HttpClient` chuẩn có từ Java 11 nên không thể dùng khi biên dịch với `--release 9`.

Không nên thay `--release` bằng cách chỉ đặt `-source` và `-target` khi cần kiểm tra API nền tảng. Hai tùy chọn đó không cung cấp cùng một kiểm tra API theo release.

### 7.2. Dùng `jdeprscan`

`jdeprscan` là công cụ JDK để quét class/JAR nhằm phát hiện việc sử dụng các API đã deprecated trong JDK.

Ví dụ:

~~~bash
jdeprscan --release 17 app.jar
~~~

Công cụ này giúp tìm các dependency đã deprecated trong phạm vi release được chọn. Kết quả có thể cần đối chiếu với source code và tài liệu migration để chọn API thay thế phù hợp.

### 7.3. Dùng `jdeps`

`jdeps` phân tích dependency của class hoặc JAR. Tùy chọn `--jdk-internals` giúp phát hiện dependency vào API nội bộ JDK:

~~~bash
jdeps --jdk-internals app.jar
~~~

Đây là bước hữu ích trước khi nâng cấp JDK. Nếu ứng dụng phụ thuộc vào internal API, hãy tìm API công khai thay thế và kiểm tra hướng dẫn di trú.

### 7.4. Dùng `javap`

`javap` hiển thị chữ ký bytecode của class:

~~~bash
javap -public java.util.List
~~~

Nó hữu ích để kiểm tra signature và modifier trong một JDK cụ thể. Tuy nhiên, `javap` không thay thế Javadoc: nó không cung cấp đầy đủ precondition, postcondition, ví dụ, ngoại lệ và hợp đồng hành vi.

### 7.5. Dùng module descriptor

Với ứng dụng modular, kiểm tra module sở hữu API:

~~~bash
jar --describe-module --file library.jar
~~~

Hoặc xem các module hệ thống có sẵn:

~~~bash
java --list-modules
~~~

Những lệnh này giúp xác nhận module name và cấu trúc module. Chúng không tự chứng minh một API đang được nhà cung cấp duy trì.

## 8. Phân biệt hỗ trợ API với hỗ trợ phiên bản JDK

Đây là phần dễ nhầm nhất khi lập kế hoạch nâng cấp.

### 8.1. Vòng đời của API

API có thể được phân loại theo tình trạng công bố:

- Standard và đang được duy trì theo hợp đồng công khai.
- Deprecated nhưng chưa bị loại bỏ.
- Deprecated và được đánh dấu `forRemoval`.
- Preview hoặc incubator.
- Internal hoặc implementation-specific.
- Đã bị loại bỏ trong release đang xem xét.

Tình trạng phải được kiểm tra theo đúng phiên bản Java và tài liệu chính thức. Một API có thể vẫn xuất hiện trong bản JDK mới dù đã deprecated từ nhiều năm trước.

### 8.2. Vòng đời hỗ trợ của JDK

JDK là một bản phân phối phần mềm có vòng đời hỗ trợ riêng. Thời gian hỗ trợ có thể khác nhau theo:

- Nhà cung cấp/bản phân phối (Oracle JDK, Eclipse Temurin, Amazon Corretto, Azul Zulu, Red Hat build of OpenJDK, v.v.).
- Phiên bản JDK và mô hình phát hành.
- Gói dịch vụ miễn phí/thương mại.
- Chính sách cập nhật bảo mật, sửa lỗi và hỗ trợ kỹ thuật.
- Hệ điều hành, kiến trúc và môi trường triển khai.

Vì vậy, không có một ngày hết hỗ trợ duy nhất áp dụng cho mọi bản phân phối Java.

Để tra cứu, hãy ghi rõ vendor và version, sau đó mở support roadmap hoặc lifecycle policy của chính vendor đó. Ví dụ Oracle Java SE Support Roadmap là chính sách của Oracle:

https://www.oracle.com/java/technologies/java-se-support-roadmap.html

Nếu đang chạy Temurin, Corretto hoặc một bản phân phối khác, hãy tra chính sách của nhà cung cấp tương ứng. Không lấy thời hạn của Oracle JDK để kết luận thời hạn hỗ trợ của một bản phân phối khác.

### 8.3. LTS không phải trạng thái của từng API

LTS (Long-Term Support) mô tả chiến lược hỗ trợ của một dòng phát hành JDK theo chính sách của nhà cung cấp. Nó không có nghĩa:

- Mọi API trong bản LTS đều được đảm bảo tồn tại mãi mãi.
- API deprecated trở lại thành API được khuyến nghị.
- Mọi nhà cung cấp đều có cùng thời hạn hỗ trợ.
- Ứng dụng không cần kiểm tra tương thích khi nâng cấp.

API lifecycle và JDK support lifecycle phải được ghi thành hai dòng riêng trong báo cáo kỹ thuật.

## 9. Quy trình tra cứu mẫu

Giả sử một dự án cần dùng `HttpClient` và phải chạy trên Java 17.

### Bước 1: Xác định API

Tên đầy đủ: `java.net.http.HttpClient`.

Module: `java.net.http`.

Package: `java.net.http`.

### Bước 2: Mở Javadoc đúng release

Mở Java SE 17 API Specification và tìm class `HttpClient`. Đọc class description, method details và mục Since.

### Bước 3: Xác nhận mốc xuất hiện

API chuẩn hóa từ Java 11. Lịch sử chuyển đổi từ incubator sang chuẩn hóa được mô tả trong JEP 110 và JEP 321.

### Bước 4: Kiểm tra trạng thái

Xác nhận class đang được công bố trong module chuẩn `java.net.http` của Java SE 17. Đọc Javadoc để kiểm tra method cụ thể có bị deprecated hoặc có điều kiện sử dụng đặc biệt không.

### Bước 5: Kiểm tra compile target

Biên dịch với `javac --release 17`. Nếu code dùng API chỉ có ở Java 21 hoặc Java 26, compiler sẽ báo lỗi khi API đó không thuộc release 17.

### Bước 6: Kiểm tra runtime và support policy

Chạy thử trên bản JDK 17 thực tế được triển khai. Sau đó tra vendor, build version và support roadmap của nhà cung cấp JDK đang dùng.

### Kết luận mẫu

| Hạng mục | Kết quả tra cứu |
|---|---|
| API | `java.net.http.HttpClient` |
| Module | `java.net.http` |
| API chuẩn từ | Java 11 |
| Java mục tiêu | Java 17 |
| Compile compatibility | Phải xác nhận bằng `javac --release 17` |
| Deprecated/preview/internal | Kiểm tra Javadoc Java 17 của class và method cụ thể |
| JDK support | Tra theo vendor và build đang triển khai |

Bảng này tách dữ kiện API khỏi dữ kiện vận hành, giúp người review thấy rõ đâu là thông tin được tài liệu Java SE bảo đảm và đâu là chính sách của nhà cung cấp.

## 10. Mẫu checklist khi review một dependency/API

Trước khi đưa API vào production hoặc nâng cấp JDK, ghi lại:

- [ ] Tên đầy đủ class/method và module/package.
- [ ] Link Javadoc của đúng phiên bản mục tiêu.
- [ ] Hợp đồng: tham số, kết quả, ngoại lệ, null, mutability, blocking và thread-safety khi liên quan.
- [ ] Mốc `@since` của phần tử cụ thể.
- [ ] Có `@Deprecated` không? Giá trị `since` là gì?
- [ ] `forRemoval` là true hay false?
- [ ] Có phải preview/incubator/internal API không?
- [ ] Nếu có JEP, đã đọc JEP và release notes liên quan chưa?
- [ ] Đã biên dịch với `javac --release N` cho phiên bản mục tiêu chưa?
- [ ] Đã chạy `jdeprscan` và `jdeps --jdk-internals` khi cần chưa?
- [ ] Vendor, JDK build và support policy đã được xác định chưa?
- [ ] Có API thay thế hoặc kế hoạch di trú nếu API deprecated/removed không?

Checklist này có thể được dùng trong pull request, review dependency, migration plan hoặc báo cáo tương thích Java.

## 11. Những lỗi tra cứu thường gặp

### Chỉ tìm trên công cụ tìm kiếm rồi dùng kết quả đầu tiên

Trang kết quả có thể thuộc JDK cũ, thư viện khác hoặc bài viết đã lỗi thời. Hãy xác nhận tên đầy đủ, module và phiên bản Javadoc.

### Dùng tài liệu mới nhất cho ứng dụng chạy trên JDK cũ

API có thể mới hơn runtime mục tiêu. Mở Javadoc đúng release và biên dịch bằng `--release` để kiểm tra.

### Nhầm `@since` với thời hạn hỗ trợ

`@since` chỉ ghi mốc xuất hiện. Nó không xác nhận API vẫn được khuyến nghị hoặc JDK chứa nó còn nhận bản vá.

### Nghĩ deprecated nghĩa là đã bị xóa

Deprecated chỉ là trạng thái không còn được khuyến nghị. Kiểm tra `forRemoval` và tài liệu migration; chỉ gọi là removed khi API thật sự không còn trong release đang xét.

### Nghĩ `forRemoval = true` cho biết ngày xóa

Annotation không ghi phiên bản loại bỏ cụ thể. Hãy kiểm tra release notes, JEP hoặc tài liệu của release đã loại bỏ API.

### Nhầm JEP với hợp đồng API

JEP mô tả đề xuất và tiến trình tính năng. Chữ ký, ngoại lệ và hành vi được cam kết phải lấy từ API Specification/Javadoc của release mục tiêu.

### Nhầm hỗ trợ của vendor với tình trạng API

Một vendor có thể còn hỗ trợ JDK cũ trong khi API trong đó đã deprecated. Một API chuẩn có thể tồn tại trên nhiều JDK nhưng các bản JDK có thời hạn hỗ trợ khác nhau.

### Dùng internal API vì thấy nó đang hoạt động

Internal API có thể đổi hoặc bị đóng mà không có cam kết tương thích. Hãy tìm public replacement và kiểm tra bằng `jdeps --jdk-internals`.

## Tóm tắt

Tra cứu một API Java cần ba lớp thông tin: hợp đồng hành vi trong Javadoc, mốc xuất hiện và lịch sử qua `@since`/JEP, cùng tình trạng hiện tại của API và vòng đời hỗ trợ của JDK. `@Deprecated(since, forRemoval)` giúp nhận diện API không còn được khuyến nghị và ý định loại bỏ; preview, incubator và internal API có mức ổn định khác API chuẩn. Dùng tài liệu của đúng Java release, `javac --release`, `jdeprscan` và `jdeps` để kiểm tra code trước khi triển khai. Khi báo cáo support, luôn ghi rõ vendor và build JDK thay vì suy ra từ `@since` hoặc nhãn LTS.

## Tài liệu tham khảo chính thức

- [Java SE 26 API Specification](https://docs.oracle.com/en/java/javase/26/docs/api/)
- [Java SE 17 API Specification](https://docs.oracle.com/en/java/javase/17/docs/api/)
- [Java SE 21 API Specification](https://docs.oracle.com/en/java/javase/21/docs/api/)
- [The Deprecated Annotation Type — Java SE API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Deprecated.html)
- [The javac Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
- [The jdeprscan Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeprscan.html)
- [The jdeps Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [JEP 110 — HTTP/2 Client (Incubator)](https://openjdk.org/jeps/110)
- [JEP 321 — HTTP Client (Standard)](https://openjdk.org/jeps/321)
- [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html)
