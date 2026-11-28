# Đọc JEP, đặc tả Java SE và tài liệu JDK để xác định hợp đồng, chi tiết triển khai và giới hạn phiên bản

> **Chương:** Phạm vi và nền tảng  
> **Module:** `JAVA_VERSION_JAVA18`  
> **Phạm vi:** Tìm hiểu các thay đổi từ Java 18 còn có ích trên JDK hiện đại, đặc biệt là UTF-8 mặc định, Simple Web Server, snippet trong Javadoc, SPI phân giải tên và cách core reflection sử dụng MethodHandle. Bài này tập trung vào **cách đọc và đối chiếu nguồn chính thức**, tránh lấy một chi tiết triển khai hoặc hướng dẫn của phiên bản cũ làm cam kết cho phiên bản đang chạy.

## 1. Mục tiêu: từ một nhận định kỹ thuật đến bằng chứng kiểm chứng được

Khi đọc “Java 18 hỗ trợ UTF-8 mặc định” hoặc “reflection dùng MethodHandle”, câu hỏi không chỉ là **đúng hay sai**. Cần hỏi thêm:

1. Đây là quy tắc của ngôn ngữ Java, hợp đồng thư viện Java SE, khả năng thuộc JDK cụ thể, hay cách triển khai bên trong JVM?
2. Tài liệu nào trực tiếp xác định quy tắc đó?
3. Quy tắc bắt đầu từ phiên bản nào; nó còn áp dụng trên JDK hiện đang dùng không?
4. Phát biểu có điều kiện, ngoại lệ, tùy chọn cấu hình hoặc giới hạn nền tảng nào?
5. Có phép thử nhỏ nào kiểm chứng hành vi được quan sát mà không suy diễn quá mức?

Ví dụ, cả ba phát biểu sau đều nói về Java 18 nhưng thuộc **ba loại thay đổi khác nhau**:

| Phát biểu | Loại bằng chứng cần tìm | Suy luận đúng |
|---|---|---|
| “Từ Java 18, default charset thường là UTF-8” | JEP 400 + `Charset.defaultCharset()` + hướng dẫn migration | Thay đổi **hành vi mặc định** của những API sử dụng default charset |
| “Từ Java 18 có `jwebserver`” | JEP 408 + **JDK tool specification** của `jwebserver` | Giới thiệu **công cụ JDK** phục vụ nội dung tĩnh, với phạm vi sử dụng đã nêu |
| “Core reflection được tái triển khai bằng method handles” | JEP 416 + API `java.lang.reflect` và `java.lang.invoke` + release notes | Thay đổi **nội bộ thực thi**; `MethodHandle` không phải API mới của Java 18 |

Không được đánh đồng “xuất hiện trong một JEP” với “trở thành API lần đầu ở phiên bản đó”, hay đánh đồng “chương trình chạy đúng trên JDK của tôi” với “được đặc tả bảo đảm trên mọi triển khai phù hợp”.

**Kết quả mong đợi:** Người học biết chọn đúng nguồn, trích một đoạn hợp đồng chính xác, ghi điều kiện và giới hạn phiên bản, rồi đưa ra một phép thử phù hợp khi áp dụng thay đổi Java 18 vào dự án thật.

## 2. Bản đồ các nguồn chính thức và trách nhiệm của từng nguồn

Không có một trang duy nhất trả lời tất cả câu hỏi về Java. Hệ thống tài liệu có những tầng trách nhiệm khác nhau:

| Nguồn | Đọc khi nào? | Có thể kết luận | Không nên kết luận chỉ từ nguồn này |
|---|---|---|---|
| **JEP** (JDK Enhancement Proposal) | Cần biết vấn đề, mục tiêu, thiết kế, phạm vi và điều không hướng đến | Thay đổi **được đề xuất/triển khai** và lý do thiết kế | Mọi câu chữ giải thích trong JEP đều là hợp đồng API vĩnh viễn |
| **JLS** (Java Language Specification) | Hỏi về cú pháp, biểu thức, kiểu, overload, generic, ngoại lệ ở mức ngôn ngữ, module declaration | Quy tắc ngôn ngữ Java cho **ấn bản JLS** đang đọc | Chi tiết thuật toán thư viện, địa chỉ mạng hay cách JIT tối ưu |
| **JVMS** (Java Virtual Machine Specification) | Hỏi về class file, liên kết/verification, bytecode, tải lớp, mô hình JVM | Quy tắc của JVM và class file cho **ấn bản JVMS** đang đọc | Một lớp cụ thể bên trong HotSpot, các bước tối ưu hóa JIT |
| **Java SE API Specification** | Hỏi về lớp, phương thức, tham số, giá trị trả về, ngoại lệ, điều kiện truy cập | Hợp đồng công khai của **API Java SE** trong phiên bản đang xét | API của mọi module `jdk.*` hay chi tiết triển khai không được đặc tả |
| **JDK API Specification** | Hỏi về API do một JDK cung cấp, ví dụ `jdk.httpserver` | Hợp đồng của **API JDK** được tài liệu phiên bản đó mô tả | API ấy có mặt trong mọi triển khai chỉ cung cấp Java SE |
| **JDK tool specification / man page** | Hỏi về `javac`, `javadoc`, `jwebserver` và cờ dòng lệnh | Cách sử dụng, giá trị mặc định và giới hạn của công cụ phiên bản đó | Công cụ có mặt trên mọi Java runtime hoặc cờ từng có sẽ tồn tại mãi |
| **Release Notes / Migration Guide** | Nâng cấp và cần biết sửa đổi, loại bỏ, cảnh báo tương thích | Khác biệt thực tế và những gì cần kiểm tra khi chuyển phiên bản | Thay thế toàn bộ JLS/JVMS/API specification |
| **CSR, JDK issue, test và mã nguồn OpenJDK** | Tìm căn nguyên thay đổi hoặc điều tra lỗi cụ thể | Bằng chứng bổ trợ về ý định, lịch sử, cách JDK triển khai | Mọi hành vi quan sát được đều là cam kết tương thích lâu dài |

Đường đọc thường hiệu quả nhất:

~~~text
Câu hỏi cụ thể
      |
      v
JEP / release notes để xác định "đã thay đổi cái gì?"
      |
      v
Chọn tài liệu đúng lớp vấn đề
  +----------+------------+--------------+--------------+
  |          |            |              |              |
 JLS       JVMS       API Javadoc    JDK tool spec
ngôn ngữ   bytecode   thư viện        lệnh/công cụ
  +----------+------------+--------------+--------------+
      |
      v
Đọc điều kiện, ngoại lệ, Since, module, phiên bản
      |
      v
Biên dịch / chạy thử trên JDK mục tiêu
      |
      v
Kết luận có phạm vi + nguồn + dữ liệu kiểm chứng
~~~

**Không có xếp hạng cứng dùng được cho mọi tình huống.** Nếu câu hỏi là “`jwebserver` dùng cổng nào?”, JDK tool specification là nguồn trực tiếp hơn JLS. Nếu hỏi “ép kiểu tại biểu thức gọi làm thay đổi descriptor thế nào?”, cần kết hợp JLS với hợp đồng `MethodHandle`. Nếu hỏi “JDK 22 còn nhận cờ trở lại reflection cũ không?”, release notes là nơi giải quyết khác biệt phiên bản.

### 2.1. “Java SE” và “JDK” không phải hai tên cho một phạm vi

Trang API JDK 27 phân chia rõ:

- Các module Java SE thường có tên bắt đầu bằng `java`, ví dụ `java.base` chứa `java.nio.charset.Charset`, `java.net.InetAddress` và `java.lang.reflect.Method`.
- Các module JDK riêng thường có tên bắt đầu bằng `jdk`, ví dụ `jdk.httpserver` chứa `com.sun.net.httpserver.SimpleFileServer`.

**Hệ quả thực tế:** JEP 408 là một cải tiến của **JDK**, và `jwebserver` là công cụ JDK. Không suy ra mọi môi trường chỉ cung cấp Java SE API đều có công cụ này. Khi triển khai, hãy kiểm tra bản phân phối JDK và module đang sử dụng.

Tham khảo: [Java SE & JDK 27 API Specification — Overview](https://docs.oracle.com/en/java/javase/27/docs/api/).

## 3. Quy trình đọc một JEP đúng cách

Lấy JEP 416 làm ví dụ. Thay vì đọc phần Summary rồi kết luận “MethodHandle ra đời ở Java 18”, hãy đi theo thứ tự sau.

### Bước 1 — Xác định phiên bản, phạm vi và trạng thái

Tìm tiêu đề, mô tả, lịch sử target/release và xác nhận thay đổi được giao trong phiên bản nào. Một JEP có thể là đề xuất đang triển khai, đã được chọn cho một release, bị thay đổi thiết kế hoặc không được đưa vào đúng phiên bản dự kiến. Với những thay đổi đã phát hành, kiểm tra thêm **release notes** và **API/tool docs** của phiên bản phát hành thực tế.

Các JEP liên quan đến bài này được phát hành trong JDK 18:

| JEP | Tên chính thức | Đọc để xác định |
|---|---|---|
| [400](https://openjdk.org/jeps/400) | UTF-8 by Default | Vì sao thay default charset, trường hợp bị ảnh hưởng và tương thích |
| [408](https://openjdk.org/jeps/408) | Simple Web Server | Mục tiêu công cụ thử nghiệm/phát triển và giới hạn |
| [413](https://openjdk.org/jeps/413) | Code Snippets in Java API Documentation | Cú pháp/khả năng snippet của standard doclet |
| [418](https://openjdk.org/jeps/418) | Internet-Address Resolution SPI | Điểm mở rộng phân giải tên của `InetAddress` |
| [416](https://openjdk.org/jeps/416) | Reimplement Core Reflection with Method Handles | Phần triển khai reflection được thay thế, cùng tác động tương thích |

Bảng này xác định **thay đổi được nêu trong JEP**, không chứng minh tất cả API mà JEP nhắc tới đều mới xuất hiện ở Java 18.

### Bước 2 — Đọc Goals, Non-Goals và Motivation

Đây là ba phần giúp tránh phóng đại:

- **Goals:** Mục tiêu thực sự mà thay đổi cần đạt.
- **Non-Goals:** Phần tác giả JEP chủ động đặt ngoài phạm vi. Đây là nguồn mạnh để nhận diện cách diễn giải sai.
- **Motivation:** Vì sao cần thay đổi, thường là vấn đề của thiết kế hoặc triển khai trước đó.

Ví dụ JEP 408 thiết kế máy chủ HTTP tối giản phục vụ tệp tĩnh để thử nghiệm, xây dựng mẫu và gỡ lỗi. Nếu ai đó nói “Java 18 đã thêm một web server có thể thay thế server production”, hãy so với **mục tiêu và giới hạn** rồi xác minh bằng tài liệu `jwebserver` hiện hành. Công cụ chỉ hỗ trợ HTTP/1.1, không có HTTPS/HTTP/2, phục vụ `GET` và `HEAD`; đây là những hạn chế mà tool specification công khai.

### Bước 3 — Đọc Description cùng thiết kế API, sau đó kiểm tra lại bằng đặc tả

JEP có thể minh họa signature, cách đăng ký provider hoặc ví dụ. Những đoạn đó trả lời **tại sao thiết kế như vậy**. Khi quyết định mã production sẽ xử lý lỗi gì hoặc quyền truy cập ra sao, tìm đặc tả của chính lớp/phương thức.

Ví dụ JEP 418 giới thiệu `InetAddressResolverProvider`. Để biết provider được chọn khi nào, có bao nhiêu resolver cấp JVM, và trường hợp không tìm được provider thì dùng gì, đọc [`InetAddressResolverProvider` trên JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html), nơi mô tả trực tiếp thuật toán lựa chọn provider.

### Bước 4 — Đọc Compatibility, Risks và liên kết issue

Các mục về tương thích thường cho thấy thay đổi có thể làm lộ giả định cũ. Nhưng giải pháp chuyển tiếp nêu trong JEP có thể bị loại bỏ ở các bản sau.

Ví dụ JEP 416 từng cho phép tạm dùng cờ `-Djdk.reflect.useDirectMethodHandle=false` để quay về cách thực thi reflection cũ. Theo [JDK 22 Release Notes](https://www.oracle.com/java/technologies/javase/22-relnote-issues.html), triển khai cũ đã bị xóa và cờ này thành **no-op**. Một tài liệu viết từ thời JDK 18 có thể đúng về lịch sử mà không còn là chỉ dẫn hợp lệ cho JDK 22+.

**Nguyên tắc:** JEP là điểm xuất phát để hiểu *sự thay đổi*, rồi luôn đối chiếu đặc tả hiện tại và tài liệu nâng cấp để biết *điều còn áp dụng*.

## 4. Đọc JLS và JVMS: xác định đúng tầng ngôn ngữ hoặc máy ảo

### 4.1. Khi nào cần JLS?

[Java Language Specification, Java SE 27 Edition](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/index.html) trả lời các câu hỏi như:

- Đoạn mã có hợp lệ theo ngữ pháp và quy tắc ngôn ngữ không?
- Trình biên dịch chọn phương thức overload nào?
- Biểu thức được đánh giá theo thứ tự nào?
- Quy tắc kiểu, chuyển đổi boxing/unboxing, kiểu ngoại lệ checked là gì?
- `module-info.java` có cú pháp và quy tắc khai báo như thế nào?

Một ví dụ dễ nhầm:

~~~java
public class OverloadCheck {
    static String choose(long x) {
        return "long";
    }

    static String choose(Integer x) {
        return "Integer";
    }

    public static void main(String[] args) {
        int value = 5;
        System.out.println(choose(value)); // long
    }
}
~~~

Với `int` đầu vào, quy tắc overload lựa chọn phương thức nhận `long` qua primitive widening ở giai đoạn áp dụng thích hợp, trước khi cần boxing sang `Integer`. Đây là câu hỏi về **ngữ nghĩa ngôn ngữ**, nên phải dựa vào quy tắc method invocation/overload trong JLS; nó không liên quan tới việc core reflection của Java 18 được triển khai bằng MethodHandle.

Tương tự, khi đọc `MethodHandle.invokeExact(...)`, một phần câu hỏi về kiểu biểu thức gọi đến từ quy tắc ngôn ngữ và đặc điểm **signature-polymorphic methods**. Nhưng việc `invokeExact` kiểm tra đúng `MethodType` và ném `WrongMethodTypeException` còn phải được xác minh từ **API `MethodHandle`**. Hai nguồn bổ sung cho nhau.

### 4.2. Khi nào cần JVMS?

[Java Virtual Machine Specification, Java SE 27 Edition](https://docs.oracle.com/en/java/javase/27/docs/specs/jvms/index.html) quy định những vấn đề ở mức JVM:

- Định dạng `.class` và giới hạn phiên bản class file.
- Bytecode, stack/locals, khung thực thi và kiểm tra hợp lệ.
- Tải, liên kết, khởi tạo lớp.
- Mô tả method và field trong constant pool.
- Các quy tắc cho thao tác `invokevirtual`, `invokestatic`, `invokedynamic`...

Ví dụ, một class file biên dịch nhắm phiên bản mới có thể bị JVM cũ từ chối bằng `UnsupportedClassVersionError`. Đó là vấn đề **mức bytecode/runtime**, không nhất thiết là vì chương trình gọi API mới. Để trả lời chính xác về version của class file, cần đọc bảng phiên bản trong JVMS ứng với bản mục tiêu.

Đừng suy luận từ tên `MethodHandle` rằng mỗi lời gọi Java có MethodHandle sẽ được JIT chuyển thành một số instruction máy nhất định. JVMS quy định **hành vi JVM có thể quan sát và ràng buộc bytecode**; lựa chọn tối ưu hóa cụ thể của một VM không mặc nhiên là hợp đồng của mọi JVM.

### 4.3. Phân biệt các tầng của cùng một biểu thức

~~~text
Mã Java:      receiver.greet("An")
                   |
                   v
JLS:         Hợp lệ? Chọn overload nào? Kiểu biểu thức?
                   |
                   v
Class file:  Lệnh gọi và symbolic reference nào?
                   |
                   v
JVMS:        Liên kết/kiểm tra/thực thi lời gọi ra sao?
                   |
                   v
JDK runtime: Cơ chế tối ưu hóa thật sự của JVM?
~~~

Câu hỏi ở tầng cuối đôi khi cần mã nguồn, diagnostic tool hoặc benchmark của JDK cụ thể. Không dùng một quan sát của tầng cuối để viết quy tắc ngôn ngữ cho mọi JVM.

## 5. Đọc API Javadoc như một bản hợp đồng kỹ thuật

API specification không chỉ liệt kê tên phương thức. Người dùng API cần đọc **đầy đủ ngữ cảnh của package, class, method và các ghi chú**.

### 5.1. Trình tự đọc một phương thức

Với một API như `InetAddress.getByName(String host)` hoặc `Method.invoke(...)`, kiểm tra:

1. **Module, package, class:** Thuộc `java.base` hay module JDK khác? Có được export công khai không?
2. **Chữ ký:** Static/instance, generic, nullable, kiểu trả về, tham số, checked exception.
3. **Mô tả hành vi:** Điều kiện đầu vào, hậu điều kiện, ảnh hưởng trạng thái, side effects.
4. **Ngoại lệ:** Loại nào đến trực tiếp, trường hợp nào được bọc; các loại lỗi chỉ là ví dụ hay điều kiện đã được quy định?
5. **Phiên bản:** `Since` cho biết thời điểm xuất hiện của thành phần có gắn nhãn, cần kiểm tra đúng **member** chứ không chỉ class.
6. **Deprecation và giới hạn:** `@Deprecated`, `Deprecated for Removal`, điều kiện quyền truy cập, nền tảng, module.
7. **Thông tin bổ trợ:** `API Note`, `Implementation Requirements`, `Implementation Note` và liên kết đến tài liệu liên quan, khi tài liệu có.

Các phần `Implementation Note` có thể nói về cách một implementation vận hành. Không tự biến phần mô tả chi tiết của một triển khai thành ràng buộc bắt buộc cho mọi nơi, trừ khi đặc tả thực sự quy định. Tương tự, một `API Note` mang tính hướng dẫn sử dụng cần được đọc trong bối cảnh hợp đồng chính của phương thức.

### 5.2. Ví dụ: `Method.invoke` có từ Java 1.1

Mở [`java.lang.reflect.Method` — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Method.html):

- Lớp có `Since: 1.1`; rõ ràng API reflection này không ra đời trong Java 18.
- Hợp đồng `invoke` mô tả cách truyền đối số, chuyển đổi kiểu, kiểm tra quyền truy cập và trường hợp bọc ngoại lệ đích trong `InvocationTargetException`.
- JEP 416 giải thích vì sao JDK triển khai core reflection bằng method handles từ Java 18; **hợp đồng gọi `Method.invoke` vẫn phải tra ở API specification**.

Một kết luận có bằng chứng sẽ là:

> “`Method.invoke` là API lâu đời; từ JDK 18, core reflection được tái triển khai dùng method handles. Mã ứng dụng vẫn gọi `Method.invoke` theo hợp đồng Java SE. Để xác định lỗi do phương thức đích, đọc `InvocationTargetException.getCause()`.”

Ngược lại, phát biểu “sau Java 18, `Method.invoke` trực tiếp ném mọi ngoại lệ của phương thức đích giống `MethodHandle.invokeExact`” là suy diễn sai do nhầm **nội bộ triển khai** với **hợp đồng public API**.

### 5.3. Ví dụ: `InetAddressResolverProvider` có `Since: 18`

Mở [`InetAddressResolverProvider` — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html):

- Lớp có `Since: 18`, phù hợp với JEP 418.
- API mô tả **một resolver system-wide cho JVM**, được khởi tạo sau khi VM khởi động đầy đủ và hoạt động tra cứu đầu tiên kích hoạt việc chọn provider.
- Provider được định vị qua `ServiceLoader`; nếu có nhiều provider, **thứ tự được tìm thấy là implementation-specific**.
- Không có provider thì dùng resolver tích hợp.

Dòng “implementation-specific” là **một giới hạn được tài liệu nói rõ**. Không được viết test hoặc cấu hình dựa vào thứ tự ngẫu nhiên “provider A luôn được chọn trước provider B”. Nếu cần một provider nhất quán, hãy kiểm soát classpath/module path và quá trình đóng gói, rồi kiểm chứng trong môi trường vận hành.

### 5.4. Ba mức cần tách: required, allowed và unspecified

Khi đọc hợp đồng, hãy phân loại từng phát biểu:

| Mức | Ví dụ | Hệ quả với ứng dụng |
|---|---|---|
| **Được quy định** | `jwebserver` mặc định dùng cổng `8000`, bind loopback theo tool spec | Có thể kỳ vọng trong phạm vi công cụ/phiên bản đã ghi |
| **Được phép thay đổi** | Thứ tự resolver provider là implementation-specific | Không mã hóa giả định về một thứ tự duy nhất |
| **Không được quy định** | Chiến lược tối ưu hóa JIT cụ thể cho mọi lời gọi reflection | Không dùng làm điều kiện đúng/sai của logic nghiệp vụ |

Ngay cả khi một giá trị mặc định được tài liệu công bố, ứng dụng có thể vẫn nên chỉ định tường minh trong môi trường vận hành để tránh sai lệch cấu hình và tránh dựa vào một mặc định không cần thiết.

## 6. Đọc tài liệu công cụ JDK: hợp đồng của `jwebserver` và `javadoc`

### 6.1. `jwebserver`: đọc man page trước khi sử dụng

[JDK 27 `jwebserver` Tool Specification](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jwebserver.html) mô tả:

- Máy chủ tĩnh dành cho prototyping, testing, debugging.
- Chỉ hỗ trợ HTTP/1.1; không cung cấp HTTPS/HTTP/2.
- Phục vụ `GET`, `HEAD`; phương thức khác trả `405` hoặc `501` tùy trường hợp.
- Mặc định bind trên loopback, cổng `8000`, thư mục hiện tại.
- Có các tùy chọn `-b`, `-p`, `-d`, `-o` để điều khiển.

Ví dụ dành cho thư mục nội dung tĩnh đã tồn tại:

~~~shell
jwebserver -b 127.0.0.1 -p 8000 -d public
~~~

**Điều có thể kết luận:** Khi công cụ và phiên bản phù hợp hiện diện, lệnh trên cấu hình server phục vụ thư mục `public` qua loopback trên cổng `8000`; nội dung thực tế còn tùy thư mục và tài nguyên có sẵn.

**Điều không thể kết luận:** Công cụ có đầy đủ TLS, xác thực, routing và các đặc tính vận hành như web server production. Đó là ngoài mục tiêu và hợp đồng được công bố.

Để kiểm tra một lệnh trong JDK đang dùng, chạy `jwebserver --help` và so sánh với tài liệu **cùng phiên bản**, nhất là khi viết script triển khai sẽ được vận hành lâu dài.

### 6.2. `{@snippet}`: xác định đây là cú pháp công cụ tài liệu

JEP 413 bổ sung hỗ trợ snippet trong **standard doclet** của `javadoc`. Để biết cú pháp và cách render, đọc:

- [JavaDoc Documentation Comment Specification for the Standard Doclet — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/javadoc/doc-comment-spec.html).
- [`javadoc` Tool Specification — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javadoc.html).

Một ví dụ nhỏ:

~~~java
/**
 * Một ví dụ độc lập trong tài liệu:
 * {@snippet lang="java" :
 *     String message = "  Java 18  ".strip();
 *     System.out.println(message); // Java 18
 * }
 */
public class ApiExample {
}
~~~

Có thể tạo tài liệu:

~~~shell
javadoc -encoding UTF-8 -d api-docs ApiExample.java
~~~

Đoạn `{@snippet}` cần được xử lý bởi standard doclet hỗ trợ tính năng này. **Không** suy ra snippet được biên dịch và kiểm thử tự động; cần có test riêng để bảo đảm ví dụ vẫn đúng sau các lần sửa mã.

Một nhầm lẫn thường gặp: “JEP 413 tạo ra cú pháp mới cho mọi file Java”. Trong thực tế, nội dung snippet nằm trong **documentation comment** và thuộc cơ chế tài liệu của Javadoc; nó không làm thay đổi cú pháp chung của mọi biểu thức Java theo JLS.

## 7. Đọc tài liệu theo phiên bản: `Since`, `--release` và runtime

### 7.1. Phân biệt năm mốc kiểm tra

Một dự án có thể dùng JDK 27 để build nhưng cần chạy trên JDK 17. Tối thiểu phải phân biệt:

| Câu hỏi | Công cụ / tài liệu kiểm chứng | Không được nhầm với |
|---|---|---|
| Source code dùng cú pháp Java nào? | JLS theo phiên bản; `javac --release` hoặc `--source` | API nào đang có trong platform |
| Mã đang tham chiếu API từ phiên bản nào? | `Since` và API spec; `javac --release` | Chỉ đặt `--target` |
| Class file sinh ra yêu cầu JVM tối thiểu nào? | JVMS và định dạng class file; `javap -verbose` nếu cần | Hành vi default charset tại runtime |
| Runtime thật có hành vi gì? | Chạy trên JDK mục tiêu; API/tool docs và release notes đúng phiên bản | Chỉ compile thành công |
| JDK nội bộ tối ưu bằng cách nào? | JEP, release notes, diagnostic hoặc mã nguồn JDK cụ thể | Cam kết hoạt động giống nhau trên mọi implementation |

`--release` của `javac` quy định ngôn ngữ, class file đích **và tập API platform hỗ trợ cho release được chọn**. Nó hữu ích hơn việc chỉ dùng `--source`/`--target` khi bạn cần giới hạn API ở một release cũ. Tuy nhiên, `--release` **không giả lập runtime của bản cũ**, không thay charset của hệ thống đang chạy, không tự bảo đảm độ tương thích của thư viện bên thứ ba và không thay cho test trên JDK thực.

Kiểm tra tài liệu hiện hành: [`javac` Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html). Các giá trị `--release` được hỗ trợ là phiên bản hiện tại và một số phiên bản trước đó; **hãy xem `javac --help`**, vì không phải mọi compiler hỗ trợ mọi release cũ.

### 7.2. Thực hành kiểm chứng API Java 18 từ JDK hiện đại

Lớp `InetAddressResolverProvider` xuất hiện ở Java 18. Đặt tệp `ApiSince18.java`:

~~~java
import java.net.spi.InetAddressResolverProvider;

public final class ApiSince18 {
    private InetAddressResolverProvider resolverProvider;

    public String describe() {
        return resolverProvider == null
                ? "Không cài resolver tùy biến"
                : resolverProvider.name();
    }
}
~~~

Nếu đang sử dụng một `javac` hỗ trợ cả `--release 17` và `--release 18`, so sánh:

~~~shell
javac --release 17 ApiSince18.java
javac --release 18 ApiSince18.java
~~~

**Kết quả mong đợi:**

- Với `--release 17`, trình biên dịch từ chối tham chiếu `java.net.spi.InetAddressResolverProvider` vì API này chưa tồn tại trong release đó.
- Với `--release 18`, phần tham chiếu API hợp lệ và tệp có thể biên dịch, nếu không có lỗi khác.

Đây là phép thử về **khả năng dùng API khi biên dịch**, không phải phép thử resolver thực sự được khởi tạo hay tên máy được phân giải ra sao. Muốn kiểm tra provider selection, cần cài một provider theo SPI và chạy trong JVM mới có cấu hình rõ ràng.

### 7.3. Kiểm chứng khác biệt môi trường runtime

Với bất kỳ JDK nào đang chạy, ghi lại cấu hình trước khi so sánh:

~~~shell
java -version
javac -version
java -XshowSettings:properties -version
java --list-modules
~~~

Phần output liên quan cần ghi là phiên bản Java/JVM, vendor, cấu hình `file.encoding`/`native.encoding` nếu nghiên cứu charset, và module JDK cần dùng có hiện diện hay không. Trên Windows, macOS hoặc Linux, cách thu thập và xử lý output trong script có thể khác; đừng đặt toàn bộ logic kiểm thử phụ thuộc định dạng output thay vì API/tool contract khi có lựa chọn tốt hơn.

Đối với dự án yêu cầu nhiều JDK, nên ghi vào báo cáo:

~~~text
JDK dùng để biên dịch:
--release mục tiêu:
JDK dùng để chạy:
Nhà cung cấp JDK:
Hệ điều hành / locale:
Module/tùy chọn quan trọng:
Kết quả quan sát:
Điều khoản đặc tả liên quan:
Phần nào còn chưa được kiểm chứng:
~~~

Đây là cách biến một nhận định kỹ thuật thành kết quả có thể tái hiện.

## 8. Năm tình huống áp dụng quy trình cho Java 18

### 8.1. JEP 400 — UTF-8 mặc định: nhận diện đúng hợp đồng API

**Câu hỏi:** “Java 18 mặc định UTF-8, vậy mọi API đọc văn bản đều UTF-8 và mọi console đều hiển thị UTF-8?”

**Tra cứu:**

1. JEP 400: lý do chuẩn hóa default charset và phạm vi tương thích.
2. [`Charset` API trên JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/Charset.html): mỗi JVM có một default charset, thông thường là UTF-8 trừ khi được thay đổi bằng cách implementation-specific.
3. API cụ thể như `Files.readString(Path)`: overload này đã xác định UTF-8 trong hợp đồng riêng của nó.
4. Hướng dẫn migration cho default charset và các khác biệt của stream/console trong môi trường liên quan.

**Kết luận phù hợp:** Default charset thường là UTF-8 từ JDK 18, nhưng phải xác định **API có sử dụng default charset không**. Các API có charset riêng, giao thức mạng và console không thể bị gom vào cùng một khẳng định.

Ví dụ kiểm chứng có chủ đích:

~~~java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class CharsetEvidence {
    public static void main(String[] args) throws Exception {
        System.out.println("Default: " + Charset.defaultCharset());

        String sample = "Xin chào — 日本語";
        Path path = Path.of("sample-utf8.txt");
        Files.writeString(path, sample, StandardCharsets.UTF_8);

        String loaded = Files.readString(path, StandardCharsets.UTF_8);
        if (!sample.equals(loaded)) {
            throw new AssertionError("Sai dữ liệu sau round-trip");
        }
        System.out.println("Round-trip UTF-8: OK");
    }
}
~~~

Việc thử `Files.writeString`/`readString` với `StandardCharsets.UTF_8` chứng minh hoạt động của **charset được chỉ định rõ**, không chứng minh UTF-8 là charset của mọi dữ liệu trên máy. Nếu cần kiểm tra ảnh hưởng default charset, tạo phép thử riêng với đúng overload không truyền charset, kèm kiểm soát dữ liệu đầu vào.

### 8.2. JEP 408 — Simple Web Server: phân biệt công cụ JDK và tiêu chuẩn Java SE

**Câu hỏi:** “Tôi có thể yêu cầu bất kỳ Java 18 runtime nào cũng cung cấp lệnh `jwebserver`?”

**Tra cứu:**

1. JEP 408 xác nhận tính năng được giới thiệu ở JDK 18.
2. Trang API [`SimpleFileServer` thuộc module `jdk.httpserver`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html).
3. [`jwebserver` tool spec](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jwebserver.html) xác định lệnh, tùy chọn và giới hạn.
4. Kiểm tra bản phân phối đang dùng có `jdk.httpserver`/`jwebserver` hay không.

**Kết luận phù hợp:** Đây là khả năng công cụ/API của JDK, không phải một quy tắc cú pháp Java hoặc một web server production bắt buộc phải có trong mọi môi trường Java SE.

### 8.3. JEP 413 — Snippet trong Javadoc: kiểm tra tính năng công cụ, không suy diễn từ cú pháp code

**Câu hỏi:** “Snippet chạy được nghĩa là ví dụ Java trong Javadoc đã qua kiểm thử?”

**Tra cứu:** JEP 413 → standard doclet spec → `javadoc` command docs → test của dự án.

**Kết luận phù hợp:** Standard doclet có thể hiển thị đoạn mã, chọn vùng và markup từ Java 18. Nó không thay thế việc compile/test ví dụ. Khi thay đổi API, phải cập nhật và kiểm thử snippet như mã nguồn thông thường.

### 8.4. JEP 418 — Resolver SPI: chú ý từ khóa implementation-specific

**Câu hỏi:** “Nếu thêm hai `InetAddressResolverProvider`, có thể bảo đảm provider nào được chọn trước không?”

**Tra cứu:** JEP 418 → `InetAddressResolverProvider` API → `ServiceLoader` và môi trường đóng gói của ứng dụng.

**Kết luận phù hợp:** API ghi rõ thứ tự provider được tìm thấy là implementation-specific; chỉ resolver từ provider đầu tiên được tìm thấy được dùng để thiết lập resolver system-wide. Nếu không tìm thấy provider, JDK dùng resolver tích hợp. Không thể coi thứ tự ngẫu nhiên là bảo đảm cho nghiệp vụ.

Muốn kiểm chứng, dùng JVM mới với module path/classpath được kiểm soát và kiểm tra kết quả tra cứu. Đừng đo bằng việc chạy lại `getByName` trên cùng JVM mà bỏ qua cache hoặc trạng thái khởi tạo đã có.

### 8.5. JEP 416 — Core reflection: tách hành vi public khỏi cách chạy bên trong

**Câu hỏi:** “JEP 416 làm cho `MethodHandle` trở thành API mới và `Method.invoke` đổi cách ném ngoại lệ?”

**Tra cứu:**

1. JEP 416 nói về việc **tái triển khai core reflection**.
2. `java.lang.invoke.MethodHandle` có từ Java 7, trong khi `java.lang.reflect.Method` có từ Java 1.1.
3. `Method.invoke` vẫn mô tả hành vi public và `InvocationTargetException` trong API spec.
4. JDK 22 release notes xác nhận triển khai reflection cũ đã bị loại bỏ; cờ lựa chọn cơ chế cũ từ JEP 416 trở thành no-op.

**Kết luận phù hợp:** JEP 416 sử dụng cơ chế có từ trước để thay phần triển khai. Nó không sửa hợp đồng public của `Method.invoke` thành hợp đồng của `MethodHandle.invokeExact`.

Đây cũng là ví dụ cảnh báo về tài liệu lịch sử: tùy chọn từng hữu ích trong giai đoạn chuyển đổi có thể không còn tác dụng ở bản JDK hiện đại.

## 9. Đọc từ khóa và câu chữ kỹ thuật: tránh hiểu sai phạm vi bảo đảm

Khi đọc trang API hoặc tool spec bằng tiếng Anh, không nên bỏ qua các từ mang ý nghĩa điều kiện:

| Câu chữ | Cách đọc | Rủi ro khi bỏ qua |
|---|---|---|
| `must`, `shall`, `is required to` | Nghĩa vụ/ràng buộc theo ngữ cảnh văn bản | Biến ràng buộc thành gợi ý tùy ý |
| `may`, `can` | Có thể, được phép | Biến khả năng thành bảo đảm bắt buộc |
| `implementation-specific` | Triển khai có quyền quyết định trong phạm vi đã nêu | Phụ thuộc vào một kết quả chỉ đúng trên JVM đang thử |
| `unspecified` | Đặc tả không cam kết kết quả cụ thể ở đây | Viết logic dựa vào giá trị tình cờ quan sát được |
| `since` | Mốc API/thành phần được giới thiệu | Nhầm mốc lớp với mốc từng phương thức |
| `deprecated` / `for removal` | Có lộ trình không khuyến khích sử dụng, có thể tiến tới loại bỏ | Đưa API đang bị loại bỏ vào thiết kế dài hạn |
| `preview` / `incubating` | Tính năng ở giai đoạn thử nghiệm với vòng đời/điều kiện riêng | Coi tính năng là hợp đồng ổn định không có điều kiện |

Ngữ nghĩa chính xác của các từ vẫn phụ thuộc vào **ngữ cảnh văn bản**. Ví dụ, `implementation-specific` trong `InetAddressResolverProvider` đi cùng tuyên bố rõ ràng về thứ tự các provider; nó không có nghĩa toàn bộ hành vi resolver là “không có đặc tả”.

**Giới hạn của phép thử:** Một kiểm thử chỉ cho biết điều gì xảy ra trong môi trường và điều kiện đã chạy. Nếu tài liệu nói kết quả là implementation-specific, việc chạy 1.000 lần cùng JVM vẫn không biến kết quả ấy thành cam kết cho tất cả triển khai.

## 10. Xây dựng “hồ sơ bằng chứng” cho một quyết định nâng cấp

Một nhóm phát triển cần kết luận: “Có thể nâng ứng dụng từ JDK 17 lên JDK 27 mà không phụ thuộc hành vi cũ của default charset không?”. Thay vì chỉ chạy `java -version` và thông báo “đã tương thích”, có thể lập hồ sơ:

| Trường | Ví dụ áp dụng cho charset |
|---|---|
| **Giả định cần kiểm chứng** | Những nơi đọc/ghi dữ liệu bên ngoài đã ghi rõ encoding |
| **Thay đổi liên quan** | JEP 400, có hiệu lực từ Java 18 |
| **Nguồn quy định** | `Charset` API trên JDK mục tiêu; hợp đồng API đọc/ghi cụ thể |
| **Nơi code có thể bị ảnh hưởng** | `new String(bytes)`, `String.getBytes()`, reader/writer không truyền charset |
| **Điều kiện môi trường** | Hệ điều hành, locale, `file.encoding`, encoding của dữ liệu cũ |
| **Phép thử** | Round-trip tiếng Việt/Unicode; bộ dữ liệu thực theo charset nguồn; so sánh JDK 17 và JDK mục tiêu |
| **Kết luận giới hạn** | Luồng dữ liệu đã kiểm thử đọc/ghi đúng trên cấu hình đã ghi; các nguồn khác cần đánh giá riêng |
| **Hành động** | Đưa charset tường minh vào ranh giới trao đổi dữ liệu; bổ sung test hồi quy |

Mẫu ngắn có thể tái sử dụng:

~~~text
Nhận định:
Phạm vi (ngôn ngữ / Java SE API / JDK API / tool / triển khai):
Phiên bản giới thiệu:
Phiên bản JDK đang dùng:
Nguồn quy định + phần liên quan:
Điều kiện, ngoại lệ, hành vi implementation-specific:
Mã hoặc cấu hình tối thiểu để kiểm chứng:
Kết quả thực tế:
Kết luận có thể bảo đảm:
Phần chưa được bảo đảm:
~~~

Cách ghi như vậy giúp người review phân biệt **điều biết chắc theo đặc tả** với **giả định kỹ thuật cần thử nghiệm**. Nó cũng giữ cho quyết định hữu ích sau khi nâng từ JDK hiện tại sang phiên bản mới hơn.

## 11. Bài tập thực hành có hướng dẫn đánh giá

### Bài 1 — Chọn nguồn đúng cho từng câu hỏi

Chọn nguồn đầu tiên cần đọc, rồi chỉ ra nguồn thứ hai dùng để đối chiếu:

1. “Trong một biểu thức overload, vì sao `int` chọn `long` thay vì `Integer`?”
2. “Một JVM cũ có thể nạp class file được biên dịch cho phiên bản mới hay không?”
3. “`InetAddressResolverProvider` chọn provider khi nào?”
4. “`jwebserver` mặc định bind ở địa chỉ nào?”
5. “JDK 22 có còn cờ để quay lại reflection cũ không?”

**Tiêu chí đạt:** Lần lượt chọn JLS, JVMS, API `InetAddressResolverProvider`, `jwebserver` tool spec, release notes JDK 22. Giải thích được vì sao JEP chỉ là nguồn bổ trợ trong từng câu hỏi.

### Bài 2 — Phân biệt API mới và triển khai mới

Mở JEP 416, `MethodHandle` Javadoc và `Method` Javadoc. Ghi ba câu có dẫn nguồn: mốc xuất hiện của từng API; phần JDK 18 đã thay; hợp đồng public còn áp dụng khi gọi `Method.invoke`.

**Tiêu chí đạt:** Không tuyên bố MethodHandle được phát minh ở Java 18; không tự đổi loại ngoại lệ của `Method.invoke`.

### Bài 3 — Thử `--release` để xác nhận giới hạn API

Sử dụng `ApiSince18.java` ở phần 7.2, biên dịch với `--release 17` và `--release 18` nếu compiler hỗ trợ cả hai. Ghi thông báo lỗi (nếu có), phiên bản compiler và giải thích kết quả.

**Tiêu chí đạt:** Chỉ kết luận về API availability/source compatibility, chưa kết luận về runtime lookup của resolver.

### Bài 4 — Xác định giới hạn môi trường

Mở JEP 400, `Charset` API và một API đọc văn bản có overload nhận `Charset`. Viết lại một luồng đọc/ghi dữ liệu ngoài để dùng charset tường minh, thử bằng chuỗi tiếng Việt và dữ liệu có dấu.

**Tiêu chí đạt:** Không dùng default charset làm nguồn sự thật cho dữ liệu được gửi từ hệ thống khác.

### Bài 5 — Bác bỏ suy luận không được đặc tả

Một đồng nghiệp nói: “Chạy thử trên máy tôi thấy resolver provider A luôn được chọn trước, nên ta dùng đó làm cơ chế ưu tiên.” Hãy dẫn một đoạn API specification phản biện, rồi đề xuất phép thử/cấu hình thay thế.

**Tiêu chí đạt:** Chỉ ra từ khóa `implementation-specific` ở thứ tự provider, đề xuất đóng gói/đăng ký một provider theo yêu cầu thay vì phụ thuộc thứ tự.

## 12. Cách tiếp tục tra cứu khi JDK thay đổi

Tại thời điểm soạn bài (tháng 11/2026), Java SE 27 đã có bản tài liệu phát hành chính thức. Khi đang làm việc với JDK khác, hãy **thay số phiên bản ở trang tài liệu** bằng đúng bản đang chạy. Nếu tính năng được giới thiệu ở Java 18 vẫn tồn tại ở bản mới, sử dụng **hợp đồng mới nhất của phiên bản mục tiêu** để đưa ra kết luận.

Thói quen tra cứu bền vững:

1. Ghi JDK/JVM version và vendor thực tế.
2. Đọc JEP để xác định **động cơ, phạm vi thay đổi**.
3. Đọc JLS/JVMS hoặc API/tool specification tương ứng để xác định **phần được bảo đảm**.
4. Đọc release notes/migration guide của các bản đi qua để phát hiện **đổi hành vi, deprecation hoặc removal**.
5. Kiểm chứng mã và cấu hình trên **môi trường mục tiêu**; lưu điều kiện tái hiện.
6. Nếu kết quả trái tài liệu, kiểm tra khác biệt version, vendor, cấu hình và các issue đã biết trước khi kết luận đặc tả sai.

Tránh phụ thuộc vào tùy chọn chỉ có ở bản cũ, implementation detail hoặc feature preview đã đổi vòng đời. Đây là cách áp dụng yêu cầu **chỉ giữ các kiến thức còn có giá trị trên JDK hiện đại**.

## 13. Tài liệu gốc để lưu cùng ghi chú kỹ thuật

| Chủ đề | Nguồn chính thức |
|---|---|
| Mục tiêu và phạm vi thay đổi Java 18 | [JEP 400](https://openjdk.org/jeps/400), [JEP 408](https://openjdk.org/jeps/408), [JEP 413](https://openjdk.org/jeps/413), [JEP 418](https://openjdk.org/jeps/418), [JEP 416](https://openjdk.org/jeps/416) |
| Hệ thống tài liệu Java SE/JDK theo phiên bản | [Java SE & JDK 27 Specifications](https://docs.oracle.com/en/java/javase/27/docs/specs/index.html) |
| Ngôn ngữ và JVM | [JLS 27](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/index.html), [JVMS 27](https://docs.oracle.com/en/java/javase/27/docs/specs/jvms/index.html) |
| Tổng quan các module Java SE/JDK | [API Specification — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/) |
| Hợp đồng default charset | [`Charset` API — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/Charset.html) |
| Công cụ và API Simple Web Server | [`jwebserver` Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jwebserver.html), [`SimpleFileServer` API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html) |
| Javadoc snippet | [JavaDoc Comment Specification — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/javadoc/doc-comment-spec.html), [`javadoc` Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javadoc.html) |
| Resolver SPI | [`InetAddressResolverProvider` API — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html) |
| Reflection và MethodHandle | [`Method` API — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Method.html), [`MethodHandle` API — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandle.html) |
| Biên dịch theo release | [`javac` Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html) |
| Tương thích khi nâng cấp | [Oracle JDK 27 Migration Guide](https://docs.oracle.com/en/java/javase/27/migrate/index.html), [JDK 18 Release Notes](https://www.oracle.com/java/technologies/javase/18-relnote-issues.html), [JDK 22 Release Notes](https://www.oracle.com/java/technologies/javase/22-relnote-issues.html) |

**Điểm mấu chốt:** JEP giúp hiểu *vì sao và điều gì thay đổi*, đặc tả Java SE và tài liệu API/tool giúp xác định *hành vi nào được bảo đảm*, còn release notes và phép thử trên JDK mục tiêu giúp trả lời *giới hạn phiên bản và môi trường nào còn áp dụng*. Chỉ khi tách được ba lớp bằng chứng này, người học mới có thể sử dụng những cải tiến Java 18 một cách chính xác và duy trì được trên JDK hiện đại.
