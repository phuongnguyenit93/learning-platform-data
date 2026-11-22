# Phương thức `abstract` trong `enum` và trách nhiệm của các hằng

Trong Java, `enum` biểu diễn một tập hợp hữu hạn các hằng đã biết trước, chẳng hạn các phép toán, trạng thái hoặc loại sự kiện. Khi hành vi của từng hằng khác nhau, enum có thể khai báo một phương thức `abstract` và giao cho từng hằng trách nhiệm triển khai phương thức đó. Trình biên dịch kiểm tra hợp đồng này ngay khi biên dịch.

## 1. Phương thức abstract tạo một nghĩa vụ biên dịch

Phương thức `abstract` trong thân enum chỉ khai báo chữ ký và không có phần triển khai. Khi đó, mỗi hằng phải có *constant-specific class body* triển khai phương thức tương ứng. Nếu thiếu một hằng, sai tên hoặc sai chữ ký, toàn bộ enum không biên dịch được.

Cách này khác với việc viết một phương thức thông thường trong enum: phương thức có thân tạo hành vi chung và chỉ các hằng thực sự cần thay đổi mới phải override. `@Override` giúp trình biên dịch phát hiện lỗi chữ ký khi định nghĩa phần triển khai riêng.

Phần sau dùng chính ràng buộc này để tách quy tắc kiểm tra chung khỏi công thức tính phí riêng của từng hằng.

## 2. Ví dụ hoàn chỉnh có thể chạy

Lưu nội dung dưới đây vào tệp `EnumAbstractMethodDemo.java`. Mỗi lựa chọn giao hàng phải cung cấp cách tính phí, nhưng tất cả đều dùng chung bước kiểm tra số lượng. Dùng Java 17 trở lên.

~~~java
public class EnumAbstractMethodDemo {
    enum DeliveryFee {
        STANDARD {
            @Override
            protected int feeInCents(int itemCount) {
                return 200 + itemCount * 100;
            }
        },
        EXPRESS {
            @Override
            protected int feeInCents(int itemCount) {
                return 500 + itemCount * 200;
            }
        },
        PICKUP {
            @Override
            protected int feeInCents(int itemCount) {
                return 0;
            }
        };

        protected abstract int feeInCents(int itemCount);

        public final int quote(int itemCount) {
            if (itemCount <= 0) {
                throw new IllegalArgumentException("itemCount must be positive");
            }
            return feeInCents(itemCount);
        }
    }

    public static void main(String[] args) {
        for (DeliveryFee delivery : DeliveryFee.values()) {
            System.out.printf(
                "%s: %d cents%n",
                delivery,
                delivery.quote(2)
            );
        }
    }
}
~~~

Biên dịch và chạy:

~~~text
javac EnumAbstractMethodDemo.java
java EnumAbstractMethodDemo
~~~

Đầu ra:

~~~text
STANDARD: 400 cents
EXPRESS: 900 cents
PICKUP: 0 cents
~~~

Dòng `delivery.quote(2)` chạy kiểm tra đầu vào chung rồi mới gọi phương thức `feeInCents(2)` của hằng hiện tại. STANDARD tính `200 + 2 × 100 = 400`, EXPRESS tính `500 + 2 × 200 = 900`, còn PICKUP không thu phí. Nếu truyền `0`, `quote` ném `IllegalArgumentException` trước khi tính toán.

Ở đây `feeInCents` là `abstract` nên **từng hằng bắt buộc triển khai**. `quote` là phương thức cụ thể `final` nên các hằng không thể bỏ qua chính sách kiểm tra chung bằng cách override nó. Nếu thêm hằng `DRONE` mà quên triển khai `feeInCents`, trình biên dịch báo lỗi ngay.

Ví dụ sử dụng `int` và phí tính bằng cent để tập trung vào cơ chế của enum. Ứng dụng tính tiền thật còn phải kiểm tra giới hạn số lượng và tránh tràn số, hoặc chọn biểu diễn số tiền phù hợp với yêu cầu nghiệp vụ.

## 3. Trách nhiệm của từng hằng

- **Thực hiện đúng chữ ký:** mỗi hằng cung cấp `feeInCents(int)` với mức truy cập phù hợp; `@Override` giúp kiểm tra hợp đồng ở thời điểm biên dịch.
- **Chỉ giữ logic riêng:** STANDARD, EXPRESS và PICKUP tính phí theo ba quy tắc khác nhau. Việc kiểm tra `itemCount` chỉ xuất hiện một lần trong `quote`.
- **Phân phối hành vi đa hình:** nơi gọi chỉ cần kiểu `DeliveryFee` và phương thức `quote`; phần triển khai `feeInCents` được chọn theo hằng đang dùng.
- **Buộc xử lý khi mở rộng:** một hằng mới không có cách tính phí sẽ gây lỗi biên dịch, thay vì âm thầm dùng một giá trị mặc định không phù hợp.

Các hằng enum vẫn là những đối tượng được khai báo trước. Chúng có thể có class body riêng nhưng không được tạo thêm bằng `new` từ bên ngoài.

## 4. Phương thức abstract và phương thức có thân mặc định

| Cách thiết kế | Trách nhiệm của các hằng |
| --- | --- |
| Phương thức `abstract` | Mọi hằng đều phải triển khai phương thức. Dùng khi mỗi hằng bắt buộc có hành vi riêng. |
| Phương thức thông thường có thân | Các hằng kế thừa hành vi mặc định; hằng nào cần khác biệt có thể ghi đè. |
| `switch` ở nơi gọi | Nơi gọi phải chọn hành vi theo từng hằng; khi thêm hằng có thể phải cập nhật nhiều điểm gọi. |

Không phải enum nào cũng cần phương thức abstract. Nếu mọi hằng có cùng hành vi, một phương thức thông thường thường đơn giản hơn. Nếu chỉ một vài hằng cần khác biệt và có một mặc định hợp lý, phương thức có thân cũng có thể phù hợp. Hãy dùng phương thức abstract khi muốn trình biên dịch đảm bảo mọi hằng đều xác định hành vi bắt buộc.

## 5. Lỗi thường gặp

1. **Bỏ triển khai ở một hằng:** enum không biên dịch được nếu một hằng không triển khai phương thức abstract.
2. **Sai chữ ký:** thay đổi tham số, kiểu trả về hoặc mức truy cập theo hướng không hợp lệ có thể làm việc ghi đè thất bại. Giữ `@Override` để trình biên dịch kiểm tra.
3. **Quên dấu `;` sau danh sách hằng:** khi enum còn khai báo phương thức, trường hoặc constructor phía sau, phải kết thúc danh sách hằng bằng dấu chấm phẩy.
4. **Viết thân cho phương thức abstract:** phương thức abstract chỉ khai báo chữ ký, không chứa phần thân trong `{ ... }`.
5. **Dùng modifier không tương thích:** phương thức abstract không thể đồng thời là `private`, `static` hoặc `final`, vì các modifier này không phù hợp với việc ghi đè triển khai.
6. **Đặt logic phân nhánh lại ở mọi nơi gọi:** nếu enum đã mô hình hóa hành vi bằng phương thức, hãy cân nhắc gọi trực tiếp phương thức đó thay vì lặp lại `switch` ở nhiều nơi.

## 6. Khi nào nên dùng

Phương thức abstract trong enum phù hợp khi tập hợp lựa chọn là hữu hạn, ổn định và mỗi lựa chọn cần thực hiện cùng một thao tác theo cách riêng, ví dụ các chính sách tính phí theo loại, quy tắc xử lý trạng thái hoặc định dạng đầu ra theo loại sự kiện.

Nếu hành vi phức tạp, thay đổi thường xuyên hoặc cần mở rộng bằng các triển khai do bên ngoài cung cấp, hãy cân nhắc interface cùng các lớp chiến lược riêng. Enum phù hợp nhất khi danh sách hằng được kiểm soát và việc thêm một hằng mới nên buộc mã nguồn xử lý rõ hành vi của hằng đó.

## 7. Ghi nhớ

- Khai báo phương thức abstract trong enum khi mọi hằng phải cung cấp một hành vi cụ thể.
- Mỗi hằng triển khai phương thức bằng thân lớp riêng và phải khớp chữ ký.
- Mã gọi sử dụng kiểu enum chung; đa hình chọn triển khai đúng lúc chạy.
- Dùng phương thức có thân mặc định khi không cần bắt buộc từng hằng triển khai.
- Biên dịch lại sau khi thêm hằng mới để phát hiện các triển khai còn thiếu.