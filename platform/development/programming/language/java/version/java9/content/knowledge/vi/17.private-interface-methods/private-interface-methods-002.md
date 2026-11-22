# Phương thức private có phần thân trong interface (Java 9+)

## 1. Mục đích

Từ Java 9, interface có thể khai báo phương thức `private` có phần thân. Tính năng này cho phép các phương thức `default` và phương thức `static` trong cùng interface dùng chung phần xử lý nội bộ mà không phải sao chép mã hoặc đưa helper đó thành API công khai.

Có hai dạng:

- **Private instance method:** có thể được gọi từ các phương thức instance khác trong cùng interface, chẳng hạn `default` method hoặc một private instance method khác.
- **Private static method:** có thể được gọi từ các phương thức static và instance khác trong cùng interface.

Các phương thức private chỉ phục vụ triển khai nội bộ. Lớp triển khai interface, lớp con của lớp triển khai và mã bên ngoài không thể gọi hoặc kế thừa chúng.

**Special Note:** Nội dung tập trung vào quy tắc ngôn ngữ Java vẫn được hỗ trợ hiện nay. Private interface methods được giới thiệu ở Java 9 và vẫn là tính năng hợp lệ, không phải API legacy. Ví dụ dùng cú pháp Java 9 để xác minh mốc phiên bản giới thiệu; dự án thực tế nên chọn target theo baseline Java đang được hỗ trợ.

## 2. Vì sao interface cần private method?

Interface có thể cung cấp hành vi dùng chung qua phương thức `default` và tiện ích dùng chung qua phương thức `static`. Khi nhiều phương thức cần cùng một bước chuẩn hóa hoặc kiểm tra dữ liệu, việc lặp lại phần xử lý khiến mã khó bảo trì. Nếu biến helper thành phương thức public, người dùng interface sẽ nhìn thấy một chi tiết triển khai mà họ không cần sử dụng.

Private method giải quyết trường hợp đó bằng cách giữ helper bên trong interface.

Ví dụ, hai phương thức mặc định cần chuẩn hóa chuỗi trước khi tạo kết quả:

- `formatForDisplay` bọc nội dung trong dấu ngoặc.
- `formatForAudit` thêm tiền tố dùng cho log.

Cả hai gọi một private instance method `normalize`. Khi quy tắc chuẩn hóa thay đổi, chỉ cần cập nhật một nơi.

Tương tự, một phương thức static public có thể dùng private static helper để kiểm tra dữ liệu và rút gọn chuỗi trước khi trả kết quả.

## 3. Cú pháp và quy tắc truy cập

Private instance method:

```java
interface Example {
    default String display(String value) {
        return normalize(value);
    }

    private String normalize(String value) {
        return value == null ? "" : value.trim();
    }
}
```

Private static method:

```java
interface Example {
    static String preview(String value) {
        return shorten(value.trim());
    }

    private static String shorten(String value) {
        return value.length() > 12
                ? value.substring(0, 12)
                : value;
    }
}
```

Các quy tắc cần nhớ:

1. Private interface method phải có phần thân. Không thể khai báo nó như một phương thức abstract.
2. Một private instance method không phải là `default`; nó là helper nội bộ và không được kế thừa.
3. Private static method phải có từ khóa `static` và có phần thân.
4. Phương thức private chỉ được truy cập từ phần triển khai bên trong chính interface khai báo nó.
5. Private instance method chỉ dùng được trong ngữ cảnh có đối tượng; không thể gọi trực tiếp nó từ một phương thức static.
6. Private static method không cần đối tượng và có thể được gọi từ các phương thức static hoặc instance trong cùng interface.
7. Private method không trở thành hợp đồng mà lớp triển khai phải cài đặt và cũng không thể được lớp triển khai override.

Trong interface, các phương thức thông thường là public nếu không khai báo private. Vì vậy, hãy ghi rõ `private` khi muốn giới hạn helper trong nội bộ interface.

## 4. Ví dụ hoàn chỉnh

Ví dụ dưới đây dùng cả private instance method và private static method. Hai phương thức mặc định gọi helper instance `normalize`; phương thức static public gọi các helper static `requireText` và `shorten`.

Tạo tệp `MessageFormatter.java`:

```java
package demo;

public interface MessageFormatter {
    String format(String value);

    default String formatForDisplay(String value) {
        return "[" + normalize(value) + "]";
    }

    default String formatForAudit(String value) {
        return "AUDIT:" + normalize(value);
    }

    private String normalize(String value) {
        if (value == null) {
            return "(empty)";
        }
        return value.trim().replaceAll("\\s+", " ");
    }

    static String preview(String value) {
        return shorten(requireText(value));
    }

    private static String requireText(String value) {
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalArgumentException("value must not be blank");
        }
        return value.trim();
    }

    private static String shorten(String value) {
        return value.length() > 12
                ? value.substring(0, 12)
                : value;
    }
}
```

Tạo lớp triển khai `BasicFormatter.java`:

```java
package demo;

public final class BasicFormatter implements MessageFormatter {
    @Override
    public String format(String value) {
        return value == null ? "(empty)" : value.trim();
    }

    public static void main(String[] args) {
        MessageFormatter formatter = new BasicFormatter();

        System.out.println(
                formatter.formatForDisplay("  hello    world "));
        System.out.println(
                formatter.formatForAudit("  hello    world "));
        System.out.println(
                MessageFormatter.preview("  Java private methods "));
    }
}
```

Biên dịch và chạy từ thư mục chứa thư mục `demo`:

```powershell
javac --release 9 -d out demo/MessageFormatter.java demo/BasicFormatter.java
java -cp out demo.BasicFormatter
```

Kết quả:

```text
[hello world]
AUDIT:hello world
Java private
```

Ví dụ được biên dịch với `--release 9` để xác nhận cú pháp từ phiên bản Java đã giới thiệu tính năng. Với dự án thực tế, hãy chọn `--release` theo baseline Java mà sản phẩm hiện hỗ trợ; không nên hạ target chỉ để giữ ví dụ cũ.

## 5. Phân biệt private instance và private static

| Đặc điểm | Private instance | Private static |
|---|---|---|
| Khai báo | `private ReturnType name(...)` | `private static ReturnType name(...)` |
| Có đối tượng hiện tại | Có ngữ cảnh instance | Không cần |
| Gọi từ default method | Có | Có |
| Gọi từ static method | Không trực tiếp | Có |
| Mục đích điển hình | Chia sẻ xử lý giữa các default method | Chia sẻ tiện ích giữa các phương thức static hoặc instance |

Trong ví dụ, `normalize` là instance helper vì nó được dùng trong các phương thức mặc định. `requireText` và `shorten` là static helper vì chúng phục vụ phương thức static `preview`.

Không nên biến mọi helper thành static theo thói quen. Chọn loại phương thức theo dữ liệu và hành vi mà helper cần truy cập.

## 6. Giới hạn và lỗi thường gặp

- **Thiếu phần thân:** private method không thể chỉ khai báo chữ ký rồi để lớp triển khai cung cấp phần thân. Nó phải có implementation ngay trong interface.
- **Nhầm private với default:** `default` là phương thức instance public cung cấp implementation cho lớp triển khai; private instance method chỉ là helper nội bộ.
- **Gọi từ lớp triển khai:** lớp triển khai không thể gọi `normalize`, `requireText` hoặc `shorten` trong ví dụ. Chúng không phải thành viên được kế thừa hay API của interface.
- **Gọi private instance từ static context:** phương thức static không có instance hiện tại để gọi private instance helper. Nếu logic không phụ thuộc trạng thái instance, cân nhắc private static helper.
- **Dùng helper làm điểm mở rộng:** lớp triển khai không thể override private method để thay đổi thuật toán. Nếu người dùng interface cần tùy biến hành vi, hãy thiết kế một phương thức public phù hợp, thường là phương thức abstract hoặc default tùy hợp đồng.
- **Đưa chi tiết nội bộ thành API:** nếu helper chỉ phục vụ các phương thức trong interface, để private giúp tránh cam kết hỗ trợ một phương thức mà người dùng không cần gọi.

## 7. Khi nào nên dùng?

Dùng private instance method khi nhiều phương thức instance trong interface cần chung một bước xử lý. Dùng private static method khi các phương thức static hoặc instance cần một tiện ích không phụ thuộc trạng thái đối tượng.

Một số ứng dụng phù hợp:

- Chuẩn hóa hoặc kiểm tra tham số dùng chung giữa nhiều default method.
- Tạo một phần thông điệp, định dạng hoặc phép biến đổi được nhiều phương thức trong interface sử dụng.
- Chia nhỏ logic của phương thức static public mà không mở rộng bề mặt API.
- Giữ các bước xử lý nội bộ ở một nơi để sửa lỗi và thay đổi quy tắc dễ hơn.

Không nên dùng private method chỉ để chia nhỏ một biểu thức đơn giản không được tái sử dụng. Helper nên có tên mô tả rõ mục đích và làm cho các phương thức public/default dễ đọc hơn.

## 8. Kiểm tra nhanh

Khi rà soát interface có private method, hãy xác nhận:

1. Mỗi private method đều có phần thân.
2. Private instance helper chỉ được gọi từ ngữ cảnh instance trong cùng interface.
3. Private static helper được gọi mà không cần đối tượng.
4. Lớp triển khai chỉ phụ thuộc vào phương thức public/default/static được công bố.
5. Ví dụ biên dịch với phiên bản Java mục tiêu của dự án.
6. Các phương thức public/default vẫn giữ đúng hợp đồng sau khi phần xử lý chung được tách thành helper.

Private interface methods là tính năng ngôn ngữ Java được bổ sung từ Java 9 và vẫn là cách hợp lệ để tổ chức implementation hiện nay. Chúng giúp tái sử dụng logic bên trong interface mà không làm lộ helper ra API công khai.
