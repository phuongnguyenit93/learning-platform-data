# Giới hạn truy cập và modifier không hợp lệ của thành viên interface

## 1. Phân biệt kiểu interface với thành viên bên trong

Quy tắc truy cập của chính interface khác với quy tắc của các thành viên. Một interface top-level có thể package-private nếu không ghi public. Tuy nhiên, phương thức abstract thông thường bên trong interface vẫn ngầm định public abstract; bỏ public không làm nó thành package-private.

Bài này là bảng tra cứu các tổ hợp modifier. Phần giải thích và ví dụ đầy đủ về từng loại phương thức nằm trong bài phân loại phương thức và bài phương thức abstract ngầm định public.

## 2. Ma trận modifier hợp lệ

| Thành viên | Quy tắc mặc định hoặc bắt buộc | Hạn chế quan trọng |
| --- | --- | --- |
| Field | public static final, phải có initializer | Không private, protected, volatile hoặc transient |
| Abstract method | public abstract, không có thân | Không private, protected, static hoặc final |
| Default method (Java 8+) | Instance method public có thân | Không kết hợp abstract, static hoặc private |
| Static method (Java 8+) | Public static có thân, trừ private static helper | Không abstract; không được gọi như method instance kế thừa |
| Private method (Java 9+) | Private instance hoặc private static, luôn có thân | Không abstract hoặc default |
| Member type lồng trong interface | public static theo ngầm định | Không private hoặc protected khi khai báo trực tiếp trong interface |

Các quy tắc này giải thích vì sao không thể dùng private field để giấu trạng thái trong interface. Nếu cần trạng thái riêng, đặt field trong class. Nếu cần helper method nội bộ từ Java 9, dùng private method có thân.

## 3. Một interface hợp lệ làm ví dụ đối chiếu

~~~java
interface AccessRules {
    int LIMIT = 3;

    void execute();

    default String describe() {
        return "[" + LIMIT + "]";
    }

    static boolean valid(int value) {
        return value >= 0;
    }

    private String helper(String value) {
        return value.trim();
    }

    private static String normalize(String value) {
        return value.trim();
    }

    class Metadata {
        String category() {
            return "rules";
        }
    }
}
~~~

LIMIT là field public static final. execute là public abstract. describe là phương thức instance default có thân; valid là static method có thân; helper và normalize là private helper methods. Metadata là member type public static theo ngầm định. Mã trên dùng cú pháp Java 17+.

## 4. Những tổ hợp sai thường gặp

| Khai báo sai | Vì sao không hợp lệ | Hướng sửa |
| --- | --- | --- |
| private int code = 1; | Field interface luôn public static final | Đặt trạng thái private trong class |
| protected void work(); | Interface method không có quyền protected | Dùng abstract method public hoặc private helper có thân |
| private abstract void work(); | Private helper không được abstract/override | Dùng public abstract contract hoặc private method có thân |
| static void work(); | Static method phải có thân | Viết static method có thân |
| default void work(); | Default method phải có thân | Viết thân hoặc dùng abstract declaration |
| static default void work() { } | Static và default mô tả hai loại phương thức khác nhau | Chọn một loại phù hợp |
| final default void work() { } | Method interface không được final | Dùng default hoặc static tùy ý định |
| private class Detail { } | Member type của interface public static theo ngầm định | Đặt kiểu cần ẩn bên trong class phù hợp |

Đừng ghép các dòng sai thành một chương trình duy nhất để kiểm tra: mỗi dòng minh họa một lỗi biên dịch riêng. Các phương thức interface cũng không được khai báo synchronized hoặc native. Với abstract method, không có thân; default, static và private method phải có thân.

## 5. Phiên bản Java cần lưu ý

- **Java 8:** hỗ trợ default method và static method có thân trong interface.
- **Java 9:** bổ sung private instance method và private static method để tái sử dụng logic nội bộ.
- **Java 17+:** tất cả các dạng trên có thể được dùng cùng nhau, miễn từng modifier phù hợp với loại thành viên.

Không suy ra rằng Java 9 cho phép mọi thành viên private: private field và private member type khai báo trực tiếp trong interface vẫn không hợp lệ.

## 6. Các lỗi về phạm vi thường bị nhầm

**Top-level interface** không có public có thể chỉ truy cập được trong package. Điều đó không làm các method bên trong nó trở thành package-private.

**Member type** nằm trực tiếp trong interface là public static theo ngầm định. Ngược lại, nested interface nằm trong một class tuân theo quy tắc thành viên của class bao ngoài; class có thể có nested type private.

**Abstract method** cần một triển khai tương thích ở lớp cụ thể, vì vậy class implements phải dùng public. **Private helper** chỉ hỗ trợ logic bên trong interface và không được kế thừa hoặc override. **Static method** thuộc về kiểu interface và được gọi qua tên interface.

### Checklist

1. Field có initializer và không dùng modifier trái phép chưa?
2. Abstract method có được hiểu là public dù bỏ từ khóa không?
3. Default/static/private method có thân và đúng loại không?
4. Private method chỉ được dùng làm helper nội bộ, không bị nhầm với hợp đồng implements?
5. Member type có được công khai theo quy tắc public static của interface?
6. Class cụ thể đã triển khai các abstract method bằng public chưa?

Dùng ma trận này khi đọc lỗi biên dịch. Trước khi sửa modifier, hãy xác định thành viên là field, abstract/default/static/private method hay member type; bỏ một từ khóa không đúng chưa chắc tạo ra một khai báo hợp lệ.