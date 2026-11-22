# @Documented và tài liệu API

## Annotation nào người dùng API cần nhìn thấy?

Khi đọc tài liệu của một thư viện, người học cần biết các điều kiện sử dụng lớp và phương thức: dữ liệu đầu vào hợp lệ, hạn chế sử dụng hoặc những cam kết mà bên cung cấp API công bố. Một annotation có thể biểu diễn một phần thông tin đó. Tuy nhiên, thư viện cũng có annotation chỉ phục vụ công cụ nội bộ, chẳng hạn gắn nhãn để tổng hợp số liệu.

`@Documented`, thuộc `java.lang.annotation`, là annotation đặt trên **khai báo kiểu annotation**. Nó đánh dấu rằng sự hiện diện và giá trị của annotation ấy thuộc hợp đồng công khai của phần tử được đánh dấu. Với Javadoc và bộ sinh tài liệu chuẩn, annotation có `@Documented` được hiển thị tại nơi sử dụng theo mặc định. Xem [hợp đồng của `Documented`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Documented.html).

Trong bài này, ta tạo `@ApiContract` để công bố quy tắc sử dụng và `@InternalTag` để gắn nhãn nội bộ, sau đó đối chiếu trang HTML với kết quả đọc annotation khi chương trình chạy. Các ví dụ dùng cú pháp Java 17+, không cần thư viện bên ngoài.

## Phân biệt ba loại thông tin

| Thành phần | Ví dụ | Vai trò trong bài |
| --- | --- | --- |
| Khai báo kiểu annotation | `public @interface ApiContract` | Định nghĩa tên và phần tử `value()` |
| Meta-annotation, tức annotation dùng cho kiểu annotation | `@Documented` trên `ApiContract` | Cho công cụ tài liệu biết thông tin cần công bố |
| Một lần sử dụng annotation | `@ApiContract("IDs must be positive")` trên `BookService` | Cung cấp quy tắc cụ thể cho API này |

Không đặt `@Documented` trực tiếp lên `BookService` hoặc `findTitle()`. Kiểu đích của `Documented` là `ANNOTATION_TYPE`; còn lớp và phương thức được gắn **annotation do ta định nghĩa**. Giới hạn vị trí sử dụng do `@Target` quy định và được trình biên dịch kiểm tra. Xem [`Target`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Target.html).

## Ví dụ hoàn chỉnh: cùng tồn tại khi chạy, khác nhau trong tài liệu

Lưu ba tệp dưới đây trong cùng một thư mục. Ví dụ không khai báo `package` để có thể chạy trực tiếp bằng các lệnh ở phần sau.

### Tệp `ApiContract.java`

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/** States a usage rule that API users must follow. */
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
public @interface ApiContract {
    /**
     * Describes the usage rule.
     * @return the rule
     */
    String value();
}
```

`value()` chứa mô tả quy tắc. Tên đặc biệt `value` cho phép viết gọn `@ApiContract("...")` thay vì `@ApiContract(value = "...")`. Việc có `@Documented` ở khai báo này khiến những lần dùng `@ApiContract` được công bố trong tài liệu chuẩn.

### Tệp `InternalTag.java`

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/** Holds a marker for an internal tool. */
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
public @interface InternalTag {
    /**
     * Identifies an internal processing group.
     * @return the group
     */
    String value();
}
```

`InternalTag` có cùng thời gian lưu giữ và cùng các vị trí áp dụng như `ApiContract`, nhưng không được gắn `@Documented`. Đây là thay đổi có chủ ý để phép đối chiếu chỉ tập trung vào việc công bố annotation.

### Tệp `BookService.java`

```java
/** Provides book lookup operations. */
@ApiContract("IDs must be positive")
@InternalTag("catalog-team")
public final class BookService {
    /** Creates a service. */
    public BookService() {
    }

    /**
     * Returns a display title for a positive book ID.
     * @param id the positive book ID
     * @return the display title
     * @throws IllegalArgumentException if the ID is not positive
     */
    @ApiContract("Rejects non-positive IDs")
    @InternalTag("lookup-metric")
    public String findTitle(long id) {
        if (id <= 0) {
            throw new IllegalArgumentException("id must be positive");
        }
        return "Book-" + id;
    }

    /**
     * Prints annotation availability at runtime.
     * @param args unused arguments
     */
    public static void main(String[] args) {
        System.out.println("ApiContract: "
                + BookService.class.isAnnotationPresent(ApiContract.class));
        System.out.println("InternalTag: "
                + BookService.class.isAnnotationPresent(InternalTag.class));
        System.out.println(new BookService().findTitle(7));
    }
}
```

Các chuỗi tiếng Anh trong ví dụ là dữ liệu cố định để dễ đối chiếu kết quả. Trong dự án thực tế, mô tả quy tắc nên phù hợp ngôn ngữ tài liệu mà nhóm phát hành.

### Biên dịch và chạy

Cần JDK 17 trở lên và các lệnh của cùng một JDK trong `PATH`. Chạy tại thư mục chứa ba tệp:

```shell
javac --release 17 -encoding UTF-8 ApiContract.java InternalTag.java BookService.java
java BookService
```

Stdout chính xác:

```text
ApiContract: true
InternalTag: true
Book-7
```

Cả hai annotation đều đọc được vì ví dụ chủ động dùng `RetentionPolicy.RUNTIME`. `@InternalTag` thiếu `@Documented` vẫn tồn tại khi chạy. Đây là bằng chứng rằng việc xuất hiện trong tài liệu không quyết định khả năng đọc bằng reflection.

### Sinh và kiểm tra tài liệu HTML

```shell
javadoc --release 17 -quiet -Werror --no-platform-links -d docs -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 ApiContract.java InternalTag.java BookService.java
```

`javadoc` đọc khai báo và chú thích tài liệu trong mã nguồn; bộ sinh tài liệu mặc định là standard doclet. Trong lệnh trên, `-d docs` chỉ thư mục kết quả, các tùy chọn UTF-8 giữ mã hóa nhất quán, `-Werror` khiến cảnh báo làm lệnh thất bại. `--no-platform-links` tránh tạo liên kết tự động tới tài liệu nền tảng; nó không quyết định annotation nào được hiển thị. Xem [lệnh `javadoc`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javadoc.html).

Mở `docs/BookService.html` bằng trình duyệt và xem khai báo lớp cùng phần chi tiết `findTitle(long)`:

| Vị trí kiểm tra | Điều quan sát được với ví dụ này |
| --- | --- |
| Khai báo `BookService` | Có `@ApiContract` với giá trị `"IDs must be positive"` |
| Chi tiết `findTitle(long)` | Có `@ApiContract` với giá trị `"Rejects non-positive IDs"` |
| Hai vị trí trên | Không hiển thị những lần gắn `@InternalTag` và các giá trị `"catalog-team"`, `"lookup-metric"` |
| Trang `docs/InternalTag.html` | Vẫn được tạo vì kiểu `InternalTag` là `public` và đã được đưa vào lệnh sinh tài liệu |

Phân biệt **trang tài liệu của kiểu annotation** với **annotation được in tại nơi sử dụng**. Việc không gắn `@Documented` không tự loại bỏ trang của `InternalTag`, không biến nó thành `private` và không che giấu mã nguồn hay bytecode.

Hình thức HTML, liên kết và bố cục có thể khác giữa các bản JDK. Điều cần kiểm tra ở đây là hai giá trị của `ApiContract` xuất hiện trên trang `BookService`, còn hai nhãn nội bộ không xuất hiện tại các khai báo tương ứng.

## Tài liệu, thời gian lưu giữ và kế thừa là những quyết định riêng

| Câu hỏi khi thiết kế annotation | Công cụ liên quan |
| --- | --- |
| Annotation có được trình bày trong tài liệu chuẩn tại nơi sử dụng không? | `@Documented` |
| Annotation được giữ đến giai đoạn nào? | `@Retention` |
| Annotation được dùng ở lớp, phương thức hay vị trí nào khác? | `@Target` |
| Truy vấn annotation trên lớp con có xét lớp cha không? | `@Inherited`, với phạm vi áp dụng riêng |

`@Documented` không tự đặt thời gian lưu giữ của annotation do ta định nghĩa. Nếu bỏ `@Retention` khỏi `ApiContract`, chính sách mặc định là `CLASS`, không phải `RUNTIME`; khi đó không nên kỳ vọng reflection đọc được nó. Bản thân `Documented` có retention `RUNTIME` cũng không truyền chính sách đó sang `ApiContract`. Xem [`Retention`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Retention.html).

Tương tự, công bố annotation không tự tạo quy tắc kế thừa. `@Inherited` liên quan đến việc tìm annotation trên lớp qua chuỗi lớp cha, không tạo cơ chế kế thừa annotation cho phương thức hay từ interface được triển khai. Xem [`Inherited`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Inherited.html).

## Annotation không thay thế phần giải thích và mã thực thi

Trong ví dụ, `@ApiContract("Rejects non-positive IDs")` mô tả quy tắc. Câu lệnh `if (id <= 0)` mới thực thi quy tắc và ném ngoại lệ. Nếu xóa câu lệnh kiểm tra mà giữ nguyên annotation, phương thức sẽ trả `"Book-0"` khi gọi với `0`; annotation không tự ngăn điều đó.

Vì vậy, khi công bố một annotation quy tắc sử dụng:

1. Viết chú thích cho **kiểu annotation** để giải thích ý nghĩa và cách diễn giải từng phần tử.
2. Ghi rõ điều kiện đầu vào, đầu ra và ngoại lệ của **API được đánh dấu**, như `@param`, `@return`, `@throws` trong ví dụ.
3. Cài đặt hoặc cấu hình cơ chế kiểm tra nếu quy tắc phải được cưỡng chế.
4. Kiểm thử hành vi thật và xem tài liệu được sinh ra trước khi phát hành.

`@param`, `@return` và `@throws` trong chú thích Javadoc là thẻ tài liệu, không phải các annotation Java có thể gắn `@Documented`. Tên và giá trị annotation giúp người đọc nhận diện quy tắc nhanh; phần mô tả vẫn cần giải thích đủ để họ sử dụng API đúng.

## Lựa chọn sử dụng và những lỗi thường gặp

Nên cân nhắc `@Documented` khi annotation truyền đạt thông tin mà người dùng API cần để gọi đúng hoặc hiểu đúng cam kết của thư viện. Một nhãn dành riêng cho quy trình thu thập số liệu có thể không cần công bố tại mỗi khai báo. Đây là quyết định thiết kế API, cần dựa vào ý nghĩa thực tế của annotation.

Những lỗi nên kiểm tra bằng chính ví dụ trên:

- **Đặt sai chỗ:** gắn `@Documented` lên lớp dịch vụ sẽ sai kiểu đích; hãy gắn nó lên khai báo `@interface`.
- **Cho rằng annotation tự kiểm tra dữ liệu:** thử truyền ID không hợp lệ và kiểm tra câu lệnh nào thực sự ném ngoại lệ.
- **Cho rằng không có `@Documented` thì annotation biến mất:** stdout của `InternalTag` trong ví dụ vẫn là `true`.
- **Cho rằng mọi annotation đều phải dùng `RUNTIME`:** chỉ chọn retention này khi cần đọc lúc chạy; nhu cầu tài liệu là một quyết định riêng.
- **Dùng chuỗi chứa bí mật làm nhãn nội bộ:** không hiển thị trong Javadoc không phải cơ chế bảo mật; không đưa thông tin bí mật vào annotation.
- **Thấy thiếu annotation rồi vội sửa retention:** trước tiên kiểm tra đúng trang, đúng phần chi tiết, `@Documented`, phạm vi truy cập và đầu vào của lệnh Javadoc.

Nội dung bài áp dụng cho Javadoc với standard doclet. Một doclet tùy chỉnh hoặc công cụ tài liệu khác có thể lựa chọn cách trình bày riêng; hãy kiểm tra kết quả của công cụ đang dùng.

## Thực hành có kết quả đối chiếu

Thực hiện từng thay đổi riêng lẻ trên bản sao ví dụ:

1. Bỏ `@Documented` khỏi `ApiContract`, biên dịch và sinh lại tài liệu vào một thư mục kết quả mới. Hai lần gắn `@ApiContract` không còn được hiển thị tại các khai báo trên trang `BookService`, nhưng stdout của chương trình vẫn giữ nguyên.
2. Khôi phục `@Documented`, đổi retention của `ApiContract` từ `RUNTIME` sang `CLASS`. Sinh lại tài liệu và chạy lại chương trình. Tài liệu từ các tệp nguồn vẫn hiển thị `@ApiContract`; dòng đầu của stdout đổi thành `ApiContract: false`, hai dòng sau vẫn là `InternalTag: true` và `Book-7`.
3. Khôi phục ví dụ ban đầu, bỏ câu lệnh kiểm tra `id <= 0`, rồi đổi lời gọi thành `findTitle(0)`. Kết quả cuối thành `Book-0`. Sửa lại mã để quy tắc trong tài liệu khớp hành vi.

Sau bài thực hành, cần giải thích được vì sao một annotation có thể có mặt trong HTML nhưng không đọc được khi chạy, và vì sao một annotation đọc được khi chạy vẫn có thể không được in trên trang API.