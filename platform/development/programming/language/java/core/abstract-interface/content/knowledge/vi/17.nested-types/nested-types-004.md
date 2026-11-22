# Lớp thành viên bên trong interface và modifier ngầm định

## Mục tiêu

Sau bài này, bạn có thể giải thích vì sao lớp được khai báo trực tiếp trong interface mặc định là `public static`, tạo đối tượng từ lớp đó, đọc đúng phạm vi của các modifier và tránh nhầm modifier của lớp lồng với modifier của interface.

## 1. Lớp thành viên trong interface là gì?

Java cho phép khai báo một lớp ngay trong thân interface. Khi lớp được khai báo trực tiếp ở cấp thành viên của interface, đó là **member class** (lớp thành viên). Ví dụ:

~~~java
interface Payment {
    class Receipt {
        public String render() {
            return "Receipt";
        }
    }
}
~~~

Khai báo `class Receipt` ở trên tương đương về modifier kiểu với:

~~~java
interface Payment {
    public static class Receipt {
        public String render() {
            return "Receipt";
        }
    }
}
~~~

Theo quy tắc ngôn ngữ Java, mọi **member type** được khai báo trong interface đều ngầm định là `public static`. Quy tắc này áp dụng cho lớp thành viên, interface lồng, enum và các kiểu thành viên hợp lệ khác. Vì vậy, từ khóa `public` và `static` có thể được viết tường minh để nhấn mạnh ý nghĩa, nhưng không bắt buộc.

- **`public` ngầm định:** kiểu lồng là một phần có thể truy cập công khai của API interface, tùy theo khả năng truy cập của chính interface chứa nó.
- **`static` ngầm định:** kiểu lồng không gắn với một đối tượng của interface bao ngoài. Không cần và cũng không thể tạo nó theo cú pháp của inner class cần đối tượng bao ngoài.
- **Không ngầm định `final` hoặc `abstract`:** lớp vẫn tuân theo quy tắc modifier thông thường của lớp Java; có thể khai báo `final` hoặc `abstract` khi phù hợp, nhưng không thể đồng thời dùng cả hai.
- **Không thể biến member type này thành `private` hoặc `protected`:** các modifier đó xung đột với tính `public` ngầm định của member type trong interface.

## 2. Tạo và sử dụng đối tượng

Hãy lưu chương trình sau trong tệp `InterfaceNestedClassDemo.java`. Interface `Payment` được để ở phạm vi package để cả ví dụ có thể nằm trong một tệp; lớp `Receipt` vẫn minh họa quy tắc `public static` ngầm định bên trong interface.

~~~java
interface Payment {
    String CURRENCY = "VND";

    class Receipt {
        private final String transactionId;

        public Receipt(String transactionId) {
            this.transactionId = transactionId;
        }

        public String render() {
            return "Receipt " + transactionId + " in " + CURRENCY;
        }
    }
}

public class InterfaceNestedClassDemo {
    public static void main(String[] args) {
        Payment.Receipt receipt = new Payment.Receipt("TX-101");
        System.out.println(receipt.render());
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~text
javac InterfaceNestedClassDemo.java
java InterfaceNestedClassDemo
~~~

Kết quả chuẩn:

~~~text
Receipt TX-101 in VND
~~~

Tên kiểu đầy đủ là `Payment.Receipt`. Có thể tạo đối tượng trực tiếp bằng `new Payment.Receipt("TX-101")`; không cần một đối tượng `Payment` làm đối tượng bao ngoài. `Payment` là interface nên bản thân nó không thể được khởi tạo bằng `new`.

Trong ví dụ, `CURRENCY` là trường khai báo trực tiếp trong interface nên ngầm định là `public static final`. Ngược lại, `transactionId` và `render()` nằm trong lớp `Receipt`; chúng tuân theo quy tắc truy cập và modifier thông thường của lớp. Modifier ngầm định của kiểu `Receipt` không tự động làm mọi thành viên bên trong lớp thành `public` hay `static`.

## 3. Phạm vi của modifier ngầm định

| Khai báo | Quy tắc |
|---|---|
| `class Receipt { }` trực tiếp trong interface | Kiểu thành viên ngầm định `public static` |
| `public static class Receipt { }` trực tiếp trong interface | Hợp lệ; `public static` được ghi tường minh nhưng dư thừa |
| `private class Receipt { }` hoặc `protected class Receipt { }` trực tiếp trong interface | Không hợp lệ vì modifier truy cập xung đột với `public` ngầm định |
| Trường khai báo trực tiếp trong interface | Ngầm định `public static final` |
| Phương thức khai báo trực tiếp trong interface | Theo quy tắc riêng của phương thức interface; không suy ra từ modifier của lớp lồng |
| Lớp cục bộ khai báo bên trong thân phương thức | Là lớp cục bộ, không phải member type trực tiếp của interface; không nhận quy tắc `public static` ở trên |

Một điểm dễ nhầm là **modifier của kiểu lồng và modifier của constructor là hai vấn đề khác nhau**. Nếu không khai báo constructor, Java sinh constructor mặc định có mức truy cập tương ứng với lớp. Nếu tự khai báo constructor mà bỏ modifier truy cập, constructor đó có phạm vi package-private, dù lớp `Receipt` là `public`. Khi cần cho mã ở package khác khởi tạo lớp, hãy khai báo constructor là `public`.

Lớp thành viên trong interface có thể có trường instance, constructor và phương thức instance như một lớp thông thường. Vì lớp này là `static`, nó không có tham chiếu ngầm định tới một instance bao ngoài. Nếu cần dùng hành vi instance của một đối tượng khác, hãy truyền đối tượng đó vào hoặc gọi thông qua biến tham chiếu thích hợp.

## 4. Những kiểu thành viên lồng khác

Quy tắc `public static` ngầm định cũng áp dụng cho các kiểu thành viên được khai báo trong interface, không chỉ riêng class:

~~~java
interface Registry {
    interface Reader {
        String read();
    }

    enum State {
        READY, CLOSED
    }

    record Item(String id) {
    }
}
~~~

Trong ví dụ này, `Reader`, `State` và `Item` là các kiểu thành viên của `Registry`; chúng được khai báo trong interface và có thể được tham chiếu bằng tên định danh như `Registry.Reader`, `Registry.State` và `Registry.Item`. Enum vốn có tính chất static theo quy tắc riêng của enum; record thành viên cũng là kiểu static. Record được hỗ trợ từ Java 16, nên ví dụ tổng hợp này cần Java 16 trở lên (Java 17 đáp ứng yêu cầu).

Không nên nhầm những kiểu thành viên công khai này với lớp trợ giúp nội bộ. Nếu một lớp chỉ phục vụ riêng cho một implementation và không nên xuất hiện trong API, hãy cân nhắc đặt nó ở phạm vi phù hợp bên ngoài interface hoặc bên trong lớp triển khai, thay vì khai báo trực tiếp trong interface.

## 5. Lỗi thường gặp và cách tránh

1. **Cố tạo lớp lồng như inner class:** viết `payment.new Receipt(...)` hoặc cho rằng phải có instance bao ngoài. Cách đúng là `new Payment.Receipt(...)`.
2. **Cho rằng lớp lồng tự động có mọi thành viên là public static:** chỉ kiểu thành viên khai báo trực tiếp trong interface nhận quy tắc `public static`; các trường, constructor và phương thức bên trong lớp lồng vẫn theo quy tắc riêng của lớp.
3. **Dùng `private` hoặc `protected` cho member type:** các modifier này không hợp lệ cho kiểu thành viên khai báo trực tiếp trong interface do kiểu đó đã ngầm định `public`.
4. **Cho rằng `static` đồng nghĩa với không thể có trạng thái:** modifier này chỉ nói rằng lớp lồng không cần instance bao ngoài. Mỗi đối tượng `Receipt` vẫn có thể giữ trạng thái riêng, như trường `transactionId`.
5. **Bỏ qua phạm vi của constructor:** khi cần cung cấp khả năng khởi tạo cho caller ở package khác, hãy đặt modifier truy cập rõ ràng cho constructor được khai báo tường minh.
6. **Đặt lớp triển khai riêng tư vào API interface:** member type của interface là public theo ngôn ngữ. Chỉ khai báo ở đây khi kiểu đó thực sự nên là một phần của API.

## 6. Quy trình kiểm tra nhanh

Khi gặp một lớp bên trong interface, hãy kiểm tra theo thứ tự:

1. Nó được khai báo trực tiếp trong thân interface hay nằm trong một phương thức/lớp khác?
2. Nếu là member type trực tiếp, hãy nhớ `public static` được ngầm định; không cần instance của interface bao ngoài.
3. Kiểm tra riêng modifier và phạm vi truy cập của constructor, trường và phương thức bên trong lớp.
4. Dùng tên có định danh interface, ví dụ `Payment.Receipt`, để làm rõ kiểu đang được tham chiếu.
5. Nếu thêm ví dụ runnable, biên dịch đúng tên tệp và kiểm tra stdout thực tế thay vì tự suy đoán kết quả.

## Kết luận

Lớp thành viên khai báo trực tiếp trong interface luôn có modifier ngầm định `public static`. Điều này quyết định khả năng truy cập kiểu và cách tạo đối tượng, nhưng không thay thế các quy tắc modifier thông thường bên trong chính lớp đó. Hiểu rõ ranh giới này giúp thiết kế API interface dễ dự đoán và tránh lỗi khi biên dịch hoặc sử dụng lớp lồng.