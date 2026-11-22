# Đọc Javadoc hiện hành và thông tin Since

## Mục tiêu

Khi học Java 8 nhưng làm việc trong hệ sinh thái Java hiện đại, cần phân biệt ba điều: **API làm gì**, **API xuất hiện từ phiên bản nào**, và **dự án có thể sử dụng API đó trên phiên bản Java mục tiêu hay không**. Javadoc chính thức là căn cứ để kiểm tra cả ba, đồng thời cho biết điều kiện đầu vào, kết quả, ngoại lệ, khuyến nghị sử dụng và trạng thái bảo trì.

Sau bài này, bạn có thể tìm và đọc đúng trang Javadoc của một lớp hoặc phương thức, diễn giải `Since` tại đúng cấp độ, phân biệt tính năng xuất hiện trong Java 8 với API bổ sung ở các bản sau, và dùng trình biên dịch để xác minh khả năng tương thích.

## 1. Javadoc hiện hành là gì?

**Javadoc** là hệ thống tài liệu API được tạo từ chú thích và khai báo trong mã Java; `javadoc` cũng là tên công cụ tạo tài liệu. Ở đây, “đọc Javadoc” nghĩa là đọc **API Specification** do nhà cung cấp JDK hoặc thư viện công bố, không chỉ đọc một ví dụ trích dẫn trên mạng.

Trong Javadoc nên chú ý đồng thời:

- **Tên đầy đủ, package, module:** giúp chọn đúng `java.util.Optional` hay `java.util.stream.Stream`.
- **Khai báo và chữ ký:** kiểu trả về, generic, tham số và overload; cùng một tên phương thức có thể có nhiều chữ ký khác nhau.
- **Description:** các bảo đảm về hành vi, thứ tự, giá trị rỗng/`null`, ngoại lệ.
- **Parameters, Returns, Throws:** hợp đồng khi truyền vào, nhận về và gặp lỗi.
- **Since:** mốc phiên bản API lần đầu được giới thiệu.
- **Deprecated / Deprecated for Removal:** khuyến cáo tránh sử dụng và khả năng bị loại bỏ.
- **API Note / Implementation Requirements / Implementation Note:** lời khuyên sử dụng, điều kiện triển khai bắt buộc, hoặc thông tin về một cách triển khai.

Một nguyên tắc quan trọng: **Javadoc của JDK mới nhất không đồng nghĩa mọi API trong đó đều chạy được trên Java 8**. Tài liệu hiện hành mô tả API của bản JDK bạn đang mở; từng phần tử có thể ra đời ở các phiên bản khác nhau.

## 2. Tìm đúng tài liệu và đúng phần tử

Nguồn chính thức để bắt đầu:

- Tài liệu Oracle JDK 27: https://docs.oracle.com/en/java/javase/27/ (ví dụ bản JDK đã phát hành vào năm 2026; khi có bản mới hơn, chọn bản đã phát hành phù hợp).
- API Specification JDK 27: https://docs.oracle.com/en/java/javase/27/docs/api/
- API Java SE 8 để kiểm tra mốc Java 8: https://docs.oracle.com/javase/8/docs/api/
- Danh sách API mới theo mốc phiên bản: https://docs.oracle.com/en/java/javase/27/docs/api/new-list.html
- Danh sách API deprecated: https://docs.oracle.com/en/java/javase/27/docs/api/deprecated-list.html

Quy trình thao tác:

1. Xác định **tên API đầy đủ** từ import, kiểu dữ liệu hoặc code: ví dụ `java.util.Optional`. Với Java hiện đại, kiểm tra thêm module, chẳng hạn `java.base`.
2. Trên trang API Specification của phiên bản JDK đang tham khảo, dùng **Search** tìm lớp/interface rồi xác nhận đúng package.
3. Đọc phần đầu trang **Class / Interface Description** và `Since` của chính kiểu dữ liệu.
4. Tìm phương thức trong **Method Summary**, mở **Method Details** theo đúng tên và danh sách tham số. Ví dụ `Optional.orElseThrow()` khác `Optional.orElseThrow(Supplier)`.
5. Đọc mục `Since` của **phương thức cụ thể** nếu có, kèm `Returns`, `Throws`, các ghi chú và trạng thái deprecated.
6. Đối chiếu với tài liệu JDK **thấp nhất mà dự án phải hỗ trợ**; sau đó xác minh bằng công cụ build.

Dấu `/27/` trong URL cho biết **bản Javadoc đang xem**, không khẳng định toàn bộ API trong trang được giới thiệu từ Java 27.

## 3. Hiểu đúng `Since`

Trong Javadoc JDK, `Since: 1.8` nghĩa là **Java 8**, còn `Since: 9` nghĩa là **Java 9**. Đừng nhầm `1.8` thành Java 18.

Bảng ví dụ từ các API còn được sử dụng trong Java hiện đại:

| Phần tử API | `Since` | Ý nghĩa thực tế |
| --- | --- | --- |
| `java.util.Optional<T>` (lớp) | `1.8` | Lớp `Optional` có từ Java 8. |
| `Optional.isEmpty()` | `11` | Phương thức này có từ Java 11; Java 8 không gọi được. |
| `Optional.orElseThrow()` (không tham số) | `10` | Overload không tham số có từ Java 10. |
| `Optional.orElseThrow(Supplier)` | Có trong Java 8 | Có thể dùng khi cần ném ngoại lệ tùy chọn trên baseline Java 8. |
| `java.util.stream.Stream.toList()` | `16` | Phương thức này có từ Java 16. |

Điểm cần ghi nhớ: **`Since` của lớp không xác định `Since` của mọi phương thức trong lớp.** `Optional` có từ Java 8 nhưng `isEmpty()` chỉ xuất hiện từ Java 11. `Stream` có từ Java 8 nhưng `Stream.toList()` chỉ có từ Java 16. Với tên phương thức có nhiều overload, kiểm tra **đúng chữ ký** từng overload.

Một phần tử không hiện `Since` ở vị trí bạn đang đọc **không cho phép kết luận** nó có sẵn từ ngày lớp được tạo. Phương thức có thể được kế thừa, có tài liệu nằm ở lớp/interface khai báo, hoặc cần đối chiếu Javadoc của phiên bản Java đích.

`Since` cho biết **thời điểm giới thiệu**, không bảo đảm API vẫn được khuyến khích dùng, không bị deprecated, không bị loại bỏ, hay giữ nguyên mọi chi tiết qua các bản phát hành. Với **thư viện bên thứ ba**, `@since` thường là số phiên bản **của thư viện**, ví dụ `2.4.0`, chứ không nhất thiết là phiên bản Java.

## 4. Đọc hợp đồng của API cùng với `Since`

Ví dụ: tra `Stream.toList()` trong tài liệu hiện hành. Ngoài `Since: 16`, Javadoc cho biết kết quả là một `List` **không thể thay đổi cấu trúc** bằng các thao tác như `add` hoặc `remove`; gọi thao tác sửa đổi sẽ ném `UnsupportedOperationException`. Nếu stream có thứ tự gặp phần tử (`encounter order`), danh sách giữ thứ tự đó. Không có bảo đảm về lớp triển khai cụ thể hoặc việc đồng nhất các đối tượng danh sách.

Đừng tùy tiện thay `Stream.toList()` bằng `collect(Collectors.toList())` rồi cho rằng mọi hành vi giống nhau: Javadoc của `Collectors.toList()` **không bảo đảm** danh sách trả về có thể sửa được hoặc có kiểu triển khai xác định. Nếu **cần danh sách sửa được**, thể hiện chủ đích bằng `Collectors.toCollection(ArrayList::new)`.

Ví dụ thứ hai: `Optional` hiện hành ghi rõ đối tượng này chủ yếu phù hợp làm **kiểu trả về** khi có thể không có kết quả; không nên tạo biến `Optional` mang giá trị `null`. Ở `Optional.get()`, `API Note` gợi ý ưu tiên `orElseThrow()` khi phù hợp. Nhưng overload `orElseThrow()` không tham số bắt đầu từ Java 10; khi còn hỗ trợ Java 8, có thể dùng `orElseThrow(NoSuchElementException::new)` vì overload nhận `Supplier` đã có từ Java 8.

Kết luận cần rút ra từ một trang Javadoc là **hợp đồng sử dụng + mốc phiên bản + trạng thái hiện nay**, không chỉ là tên phương thức.

## 5. Ví dụ JDK 17+: cùng lớp Java 8 nhưng sử dụng API mới hơn

Lưu thành tệp `JavadocSinceDemo.java`:

~~~java
import java.util.List;
import java.util.Optional;
import java.util.stream.Stream;

public class JavadocSinceDemo {
    public static void main(String[] args) {
        Optional<String> nickname = Optional.of("Lan");

        System.out.println(nickname.orElse("Guest"));
        System.out.println(nickname.isEmpty());

        List<String> names = Stream.of("an", "binh", "chi")
                .map(String::toUpperCase)
                .toList();

        System.out.println(names);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac JavadocSinceDemo.java
java JavadocSinceDemo
~~~

Kết quả chính xác:

~~~text
Lan
false
[AN, BINH, CHI]
~~~

Phân tích:

- `Optional.of(...)`, `Optional.orElse(...)` và các thao tác stream cơ bản có từ Java 8.
- `Optional.isEmpty()` có từ **Java 11**.
- `Stream.toList()` có từ **Java 16**.
- Vì vậy chương trình này chạy trên JDK 17+, nhưng **không tương thích API Java 8**, dù `Optional` và `Stream` là các lớp/interface có từ Java 8.

Trên JDK hiện đại có hỗ trợ `--release 8`, thử kiểm tra baseline:

~~~bash
javac --release 8 JavadocSinceDemo.java
~~~

Phép biên dịch này sẽ **thất bại** vì API đích Java 8 không chứa `Optional.isEmpty()` và `Stream.toList()`. Không dựa vào đúng từng dòng thông báo lỗi của `javac` vì cách trình bày lỗi thay đổi tùy JDK.

## 6. Viết phương án vẫn tương thích Java 8

Nếu dự án bắt buộc hỗ trợ Java 8, dùng API đã có ở baseline đó. Lưu thành `Baseline8Demo.java`:

~~~java
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class Baseline8Demo {
    public static void main(String[] args) {
        Optional<String> nickname = Optional.of("Lan");

        System.out.println(nickname.orElse("Guest"));
        System.out.println(!nickname.isPresent());

        List<String> names = Stream.of("an", "binh", "chi")
                .map(String::toUpperCase)
                .collect(Collectors.toList());

        System.out.println(names);
    }
}
~~~

Dùng JDK hiện đại có `--release`:

~~~bash
javac --release 8 Baseline8Demo.java
java Baseline8Demo
~~~

Kết quả:

~~~text
Lan
false
[AN, BINH, CHI]
~~~

Thay `isEmpty()` bằng `!isPresent()` vì `isPresent()` đã có từ Java 8; thay `Stream.toList()` bằng `collect(Collectors.toList())` vì collector đó đã được hỗ trợ. **Chú ý** `Collectors.toList()` không bảo đảm kết quả có thể sửa đổi. Nếu cần `ArrayList` có thể thêm phần tử, dùng cách nêu rõ kiểu:

~~~java
List<String> mutableNames = Stream.of("an", "binh", "chi")
        .collect(Collectors.toCollection(java.util.ArrayList::new));
mutableNames.add("dung");
System.out.println(mutableNames);
~~~

Kết quả của đoạn bổ sung khi đặt trong một phương thức có import `List`, `Stream`, `Collectors`:

~~~text
[an, binh, chi, dung]
~~~

Đoạn bổ sung này là **đoạn minh họa để đặt trong một phương thức**, không phải chương trình độc lập. Hai chương trình trước có `main` và tên tệp trùng với tên lớp `public` nên có thể biên dịch/chạy trực tiếp.

Lưu ý thêm: tùy chọn `--release 8` chỉ dùng được với `javac` của JDK mới có hỗ trợ; chính `javac` đi kèm Java 8 chưa có tùy chọn đó. Việc biên dịch thành công với `--release` là một bước quan trọng, nhưng không thay thế việc kiểm tra runtime và thư viện phụ thuộc thực tế.

## 7. Quy trình ra quyết định khi gặp API lạ

1. **Tìm đúng thành phần**: package → lớp/interface → phương thức **đúng overload**. Kiểm tra có phải phương thức kế thừa từ một interface khác hay không.
2. **Đọc Javadoc hiện hành**: lấy mô tả hành vi, điều kiện `null`, thứ tự, bất biến, `Throws` và các ghi chú.
3. **Đọc `Since` đúng cấp**: không lấy `Since` của lớp gán cho mọi phương thức.
4. **Kiểm tra trạng thái bảo trì**: xem `Deprecated`, `Deprecated for Removal`, `Preview` và khuyến nghị thay thế.
5. **Xác định phiên bản Java tối thiểu dự án hỗ trợ**: phân biệt JDK dùng để chạy compiler, cấu hình `--release`/toolchain, và JDK runtime trên máy chủ.
6. **Đối chiếu Javadoc phiên bản đích**: API có xuất hiện với cùng chữ ký ở bản cần hỗ trợ hay không? API mới chỉ dành cho JDK mới hơn thì không dùng trong mã còn nhắm Java 8.
7. **Biên dịch và chạy ví dụ nhỏ**: dùng `javac --release 8` nếu có yêu cầu tương thích Java 8; kiểm tra cả hành vi, không chỉ chuyện compiler chấp nhận.
8. **Ghi lý do lựa chọn**: ví dụ “dùng `isPresent()` vì baseline Java 8, còn `isEmpty()` có từ Java 11”.

Cấu hình `source`/`target` đơn lẻ không đủ để bảo đảm mã không gọi nhầm API của JDK mới; `--release` kiểm soát cả tập API chuẩn có thể dùng ở phiên bản mục tiêu. Các dependency bên ngoài và môi trường chạy vẫn cần được kiểm chứng riêng.

## 8. Đọc thêm những nhãn quan trọng

| Nhãn | Ý nghĩa | Hành động nên làm |
| --- | --- | --- |
| `Since` | Phiên bản đầu tiên giới thiệu phần tử | So với baseline của dự án |
| `Deprecated` | API không còn được khuyến khích dùng | Đọc lý do và hướng chuyển đổi |
| `Deprecated for Removal` | API được đánh dấu hướng tới loại bỏ | Chuẩn bị chuyển sang lựa chọn được hỗ trợ |
| `Preview` | API/tính năng thử nghiệm theo cơ chế của JDK | Không coi là API ổn định; kiểm tra yêu cầu bật và phiên bản |
| `API Note` | Lời khuyên, trường hợp sử dụng điển hình | Đọc trước khi áp dụng |
| `Implementation Requirements` | Yêu cầu dành cho các triển khai | Hiểu mức bảo đảm bắt buộc |
| `Implementation Note` | Ghi chú một cách triển khai | Không tự suy diễn là quy tắc cho mọi triển khai |
| `Throws` | Điều kiện phát sinh ngoại lệ | Xử lý đúng đầu vào, lỗi và `null` |
| `See Also` | Liên kết tới API liên quan | Xem lựa chọn thay thế có hợp đồng phù hợp hơn |

`@since` là **thẻ trong comment Javadoc**, còn `@Deprecated` là **annotation Java**. Đừng nhầm hai khái niệm. Một API ra đời từ Java 8 vẫn có thể là lựa chọn đúng trong ứng dụng mới nếu Javadoc hiện hành tiếp tục hỗ trợ và hợp đồng phù hợp; tuổi đời một mình không khiến API trở thành legacy.

## 9. Những sai lầm phổ biến

- **Xem Javadoc JDK mới rồi cho rằng mọi API đều dùng được trên Java 8** → tra `Since` từng thành phần và thử biên dịch ở baseline.
- **Chỉ xem `Since 1.8` trên lớp `Optional`** → kiểm tra `Since 11` của `isEmpty()` và `Since 10` của `orElseThrow()` không tham số.
- **Nhầm các overload cùng tên** → so sánh chữ ký đầy đủ.
- **Chỉ đọc bảng Method Summary** → mở Method Details để biết `Throws`, `Returns` và `API Note`.
- **Coi `Since` là lời cam kết API được bảo trì mãi** → kiểm tra deprecated, preview và việc API còn tồn tại trong phiên bản đích.
- **Giả định `Collectors.toList()` luôn trả về danh sách sửa được** → kiểm tra hợp đồng; dùng `toCollection(ArrayList::new)` khi yêu cầu danh sách sửa được.
- **Nhìn code biên dịch trên máy mình rồi kết luận tương thích Java 8** → kiểm tra `--release 8` và runtime mục tiêu.
- **Diễn giải `@since` thư viện ngoài như phiên bản JDK** → xác định hệ thống phiên bản của tài liệu đang đọc.

## 10. Bài tập tự kiểm tra

1. Mở trang `Optional` trong Javadoc hiện hành. Ghi lại `Since` của **lớp**, của `isEmpty()` và của hai overload `orElseThrow`. Nếu hỗ trợ Java 8, chọn overload nào khi muốn ném một ngoại lệ nếu rỗng?
2. Mở `Stream.toList()`. Chỉ ra `Since`, ý nghĩa `unmodifiable` và rủi ro khi đổi sang collector khác.
3. Dự đoán vì sao `Optional.of("x").isEmpty()` không biên dịch với `--release 8` dù lớp `Optional` có `Since 1.8`.
4. Với phương thức kế thừa không hiện `Since` ngay tại vị trí đang xem, bạn sẽ xác định nơi khai báo và kiểm tra API của phiên bản đích thế nào?

**Tự đánh giá đạt** khi có thể dẫn lại trang Javadoc chính thức, xác định chính xác mốc Java cho một chữ ký API, giải thích hợp đồng sử dụng và chứng minh khả năng tương thích bằng compiler.

## Tài liệu chính thức

- Java SE 27 API Specification: https://docs.oracle.com/en/java/javase/27/docs/api/
- Javadoc `Optional`: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Optional.html
- Javadoc `Stream`: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html
- Javadoc `Collectors`: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Collectors.html
- New API List: https://docs.oracle.com/en/java/javase/27/docs/api/new-list.html
- Deprecated API List: https://docs.oracle.com/en/java/javase/27/docs/api/deprecated-list.html
- Javadoc Java 8 để đối chiếu: https://docs.oracle.com/javase/8/docs/api/

Khi JDK mới ra mắt, dùng Javadoc của bản đã phát hành và kiểm tra lại trước khi áp dụng. **Không cố giữ cách dùng đã lỗi thời chỉ vì thấy trong ví dụ cũ**, cũng không bỏ API Java 8 đang được hỗ trợ chỉ vì nó ra đời sớm.