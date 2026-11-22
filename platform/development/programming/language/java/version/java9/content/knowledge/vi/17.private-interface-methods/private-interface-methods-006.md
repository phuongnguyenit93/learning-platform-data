# Giới hạn kết hợp `private` với các modifier khác trong interface

Trong Java, `private` có thể được dùng để khai báo phương thức nội bộ ngay trong `interface` từ Java 9. Quy tắc này vẫn được hỗ trợ trong các phiên bản Java hiện đại. Phạm vi bài này là **modifier của phương thức interface**; quy tắc của field và class không được áp dụng thay thế cho phương thức interface.

Một phương thức `private` trong interface phải có thân hàm. Nó chỉ phục vụ việc dùng chung logic bên trong chính interface đã khai báo phương thức đó, không trở thành API mà lớp triển khai hoặc interface con có thể gọi.

## 1. Hai cách khai báo hợp lệ

### `private` cho phương thức instance

```java
private void validate(int value) {
    if (value < 0) {
        throw new IllegalArgumentException("value must be >= 0");
    }
}
```

Đây là phương thức instance riêng của interface. Các phương thức instance khác trong cùng interface, chẳng hạn `default` method hoặc một phương thức `private` instance khác, có thể gọi nó. Vì đây không phải phương thức `static`, một phương thức `static` không thể gọi trực tiếp nó nếu không có một đối tượng phù hợp.

### `private static` cho phương thức static

```java
private static int normalize(int value) {
    return Math.max(value, 0);
}
```

`private static` là tổ hợp hợp lệ. Phương thức này có thể được gọi từ các phương thức khác trong cùng interface, kể cả phương thức `default`, phương thức instance `private` và phương thức `static`. Nó không được gọi thông qua đối tượng triển khai từ bên ngoài interface.

Cả hai dạng đều phải có thân hàm. Không được khai báo một phương thức `private` chỉ bằng chữ ký rồi chờ lớp triển khai cung cấp phần thân.

## 2. Bảng kết hợp `private` với các modifier

| Modifier kết hợp | Hợp lệ? | Giải thích |
| --- | --- | --- |
| `static` | Có | Tạo phương thức trợ giúp `private static`; phương thức phải có thân hàm. |
| `abstract` | Không | Phương thức `abstract` không có thân hàm, trong khi phương thức `private` bắt buộc phải có thân hàm và không được lớp triển khai cài đặt. |
| `default` | Không | `default` khai báo phương thức instance có phần triển khai được kế thừa; phương thức `private` là thành phần nội bộ và không được kế thừa. |
| `public` | Không | `public` và `private` là hai mức truy cập loại trừ nhau, không thể cùng khai báo trên một phương thức. |
| `protected` | Không | Phương thức khai báo trong interface không được dùng mức truy cập `protected`. |
| `final` | Không | `final` không phải modifier được phép cho khai báo phương thức interface. |
| `synchronized` | Không | `synchronized` không phải modifier được phép cho khai báo phương thức interface. |
| `native` | Không | `native` không được phép cho phương thức interface; phương thức `private` cũng cần phần thân Java. |
| `strictfp` | Có về cú pháp, nhưng không có tác dụng bổ sung từ Java 17 | Java 17 trở đi luôn dùng ngữ nghĩa floating-point nghiêm ngặt; không cần thêm `strictfp` vào mã hiện đại. |

Vì vậy, trong mã Java hiện đại, các dạng cần dùng là `private` và `private static`. `strictfp` có thể vẫn xuất hiện trong cú pháp phương thức, nhưng không thay đổi kết quả tính toán từ Java 17 trở đi và nên được bỏ khỏi mã mới.

### Vì sao `private abstract` và `private default` không hợp lệ?

- `abstract` mô tả một phương thức chưa có phần triển khai. Ngược lại, phương thức `private` phải có thân hàm và không thể được lớp triển khai ghi đè để hoàn thiện.
- `default` là phương thức instance có phần triển khai được kế thừa bởi lớp triển khai. Phương thức `private` không được kế thừa và không thể được gọi như một phương thức `default` công khai.
- `static` không tạo ra xung đột đó: một phương thức `private static` có thân hàm và chỉ được dùng bên trong interface khai báo nó.

## 3. Phạm vi truy cập và kế thừa

Phương thức `private` chỉ có thể được gọi từ mã thuộc chính interface khai báo nó. Lớp triển khai, interface con và một interface khác không thể gọi phương thức này, kể cả khi chúng nằm trong cùng package.

Phương thức `private` không được kế thừa và không thể được ghi đè. Nếu lớp triển khai tự khai báo một phương thức có cùng tên và tham số, phương thức trong lớp đó là một khai báo riêng, không phải phần ghi đè phương thức `private` của interface. Không đặt `@Override` lên phương thức `private` của interface.

Với phương thức interface không ghi `private`, nếu không ghi mức truy cập thì phương thức được hiểu là `public`. Interface không có phương thức instance với mức truy cập package-private được khai báo tường minh.

Quy tắc trong phần này nói về phương thức. Field khai báo trong interface luôn là `public static final` theo quy tắc của Java; không thể dùng `private` để biến field interface thành field riêng.

## 4. Ví dụ chạy được với Java 17+

Ví dụ sau dùng một phương thức `private` instance để kiểm tra đầu vào và một phương thức `private static` để tính giá sau giảm. Hai phương thức `default` dùng chung các phần trợ giúp này.

```java
interface DiscountPolicy {
    default int discountedPrice(int price, int percent) {
        validate(price, percent);
        return calculateDiscount(price, percent);
    }

    default int memberPrice(int price) {
        validate(price, 10);
        return calculateDiscount(price, 10);
    }

    private void validate(int price, int percent) {
        if (price < 0) {
            throw new IllegalArgumentException("price must be >= 0");
        }
        if (percent < 0 || percent > 100) {
            throw new IllegalArgumentException("percent must be between 0 and 100");
        }
    }

    private static int calculateDiscount(int price, int percent) {
        return (int) ((long) price * (100 - percent) / 100);
    }
}

public class Main {
    public static void main(String[] args) {
        DiscountPolicy policy = new DiscountPolicy() {};
        System.out.println(policy.discountedPrice(1000, 20));
        System.out.println(policy.memberPrice(500));
    }
}
```

Lưu thành `Main.java`, sau đó biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 Main.java
java Main
```

Kết quả:

```text
800
450
```

`validate` là phương thức instance `private`, được hai phương thức `default` gọi trong cùng interface. `calculateDiscount` là phương thức `private static`, phù hợp với phép tính không cần trạng thái instance. Lớp tạo đối tượng `DiscountPolicy` chỉ gọi được hai phương thức `default` công khai.

## 5. Các khai báo không hợp lệ thường gặp

Đoạn dưới đây chỉ minh họa các khai báo sai; nếu đặt tất cả vào một interface, trình biên dịch sẽ báo lỗi:

```java
interface InvalidExamples {
    private abstract void missingBody();
    private default void defaultHelper() {}
    public private void conflictingAccess() {}
    protected void protectedMethod();
    private final void finalMethod() {}
    private synchronized void synchronizedMethod() {}
    private native void nativeMethod();
}
```

Các lỗi tương ứng:

1. `private abstract`: phương thức `private` phải có thân hàm; `abstract` không thể kết hợp với `private`.
2. `private default`: phương thức `default` và phương thức `private` có mục đích truy cập khác nhau, không thể kết hợp.
3. `public private`: hai mức truy cập xung đột.
4. `protected`: interface không cho phép phương thức khai báo với mức truy cập này.
5. `private final`: `final` không được phép trong khai báo phương thức interface.
6. `private synchronized`: `synchronized` không được phép trong khai báo phương thức interface.
7. `private native`: `native` không được phép trong khai báo phương thức interface và không cung cấp thân hàm Java.

## 6. Lỗi thiết kế cần tránh

- Khai báo `private` rồi gọi phương thức từ lớp triển khai. Lớp triển khai không có quyền truy cập phương thức đó.
- Dùng `private` cho phương thức mà lớp triển khai cần ghi đè. Phương thức `private` không tham gia cơ chế ghi đè.
- Bỏ thân hàm vì nghĩ lớp triển khai sẽ bổ sung phần triển khai. Phương thức `private` trong interface phải tự có thân hàm.
- Dùng `private default` để vừa ẩn phương thức vừa cho lớp triển khai kế thừa. Hai mục đích này không thể kết hợp trên cùng một phương thức.
- Thêm `strictfp` vào phương thức mới mà không có lý do tương thích cụ thể. Từ Java 17, modifier này không làm thay đổi ngữ nghĩa tính toán floating-point.

## 7. Phiên bản Java và cách chọn modifier

Phương thức `private` trong interface được hỗ trợ từ Java 9. Khi biên dịch mã có khai báo này, cấu hình source/release phải là Java 9 trở lên; cấu hình tương thích Java 8 sẽ từ chối cú pháp.

Khi viết interface:

- Chọn `private` cho hàm trợ giúp instance chỉ được dùng bên trong interface.
- Chọn `private static` cho hàm trợ giúp không cần đối tượng instance.
- Giữ phương thức `default` hoặc `static` ở mức truy cập phù hợp nếu chúng là API mà lớp triển khai hoặc mã bên ngoài cần gọi.
- Luôn cung cấp thân hàm cho phương thức `private`.
- Không kết hợp `private` với `abstract`, `default`, `public` hoặc `protected`; không thêm `final`, `synchronized` hay `native` vào khai báo phương thức interface.