# Ví dụ theo dõi thứ tự khởi tạo bằng dấu vết thực thi

Khi đọc một chương trình Java có kế thừa, nhiều khối khởi tạo và constructor, đừng đoán thứ tự chỉ từ nơi gọi `new`. Hãy theo dõi riêng **khởi tạo lớp (class initialization)** và **khởi tạo đối tượng (instance initialization)**, rồi ghi lại từng câu lệnh có tác dụng quan sát được, chẳng hạn `System.out.println`.

Bài này dùng một chương trình nhỏ có lớp cha `Parent` và lớp con `Child`. Mỗi khối khởi tạo hoặc field initializer in ra một dấu vết. Chạy chương trình sẽ cho thấy vì sao lần tạo đối tượng đầu tiên có cả dấu vết static, còn lần tạo thứ hai chỉ có dấu vết instance.

## 1. Các quy tắc cần dùng khi lần theo dấu vết

1. **Khởi tạo lớp cha trước lớp con.** Trước khi một lớp được khởi tạo, lớp cha trực tiếp của nó phải được khởi tạo trước.
2. **Static field initializer và static block chạy theo thứ tự văn bản trong từng lớp.** Chúng chạy trong quá trình khởi tạo lớp, thường được kích hoạt bởi lần sử dụng chủ động đầu tiên như tạo đối tượng bằng `new` hoặc gọi phương thức static. Việc nạp lớp (loading) không đồng nghĩa với việc các initializer đã chạy.
3. **Static initialization chạy một lần cho mỗi lớp được khởi tạo trong một class loader.** Tạo thêm đối tượng của cùng lớp không chạy lại static block hoặc static field initializer.
4. **Với mỗi đối tượng, phần khởi tạo instance của lớp cha diễn ra trước phần instance của lớp con.** Trong từng lớp, field initializer và instance initializer block chạy theo thứ tự xuất hiện trong mã nguồn.
5. **Constructor body chạy sau các initializer của lớp tương ứng.** Constructor lớp con gọi constructor lớp cha trước khi phần thân còn lại của constructor lớp con chạy. Nếu không viết lời gọi tường minh, Java chèn lời gọi `super()` khi hợp lệ.

Các quy tắc này đủ để giải bài bằng cách chia dấu vết thành hai nhóm: sự kiện static xảy ra khi lớp được khởi tạo, và sự kiện instance xảy ra mỗi lần một đối tượng được tạo.

## 2. Chương trình Java hoàn chỉnh

Lưu toàn bộ mã dưới đây vào tệp `InitTraceDemo.java`. Thứ tự các field và block được cố ý sắp xếp để ta có thể quan sát thứ tự văn bản.

```java
class Parent {
    static {
        System.out.println("1. Parent: static block");
    }

    private static final String STATIC_VALUE =
            log("2. Parent: static field initializer");

    private final String instanceValue =
            log("5. Parent: instance field initializer");

    {
        System.out.println("6. Parent: instance initializer block");
    }

    Parent() {
        System.out.println("7. Parent: constructor body");
    }

    private static String log(String message) {
        System.out.println(message);
        return message;
    }
}

class Child extends Parent {
    static {
        System.out.println("3. Child: static block");
    }

    private static final String STATIC_VALUE =
            log("4. Child: static field initializer");

    private final String instanceValue =
            log("8. Child: instance field initializer");

    {
        System.out.println("9. Child: instance initializer block");
    }

    Child() {
        System.out.println("10. Child: constructor body");
    }

    private static String log(String message) {
        System.out.println(message);
        return message;
    }
}

public class InitTraceDemo {
    public static void main(String[] args) {
        System.out.println("=== first object ===");
        new Child();

        System.out.println("=== second object ===");
        new Child();
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```text
javac InitTraceDemo.java
java InitTraceDemo
```

## 3. Kết quả chính xác

```text
=== first object ===
1. Parent: static block
2. Parent: static field initializer
3. Child: static block
4. Child: static field initializer
5. Parent: instance field initializer
6. Parent: instance initializer block
7. Parent: constructor body
8. Child: instance field initializer
9. Child: instance initializer block
10. Child: constructor body
=== second object ===
5. Parent: instance field initializer
6. Parent: instance initializer block
7. Parent: constructor body
8. Child: instance field initializer
9. Child: instance initializer block
10. Child: constructor body
```

## 4. Đọc dấu vết theo từng giai đoạn

| Dấu vết | Điều vừa xảy ra | Lý do |
|---|---|---|
| 1 | Static block của `Parent` | Lớp cha được khởi tạo trước lớp con. |
| 2 | Static field initializer của `Parent` | Nó nằm sau static block trong mã nguồn của `Parent`. |
| 3 | Static block của `Child` | Sau khi `Parent` được khởi tạo xong, `Child` mới tiếp tục khởi tạo. |
| 4 | Static field initializer của `Child` | Nó nằm sau static block trong mã nguồn của `Child`. |
| 5–7 | Field instance, block instance, rồi constructor của `Parent` | Phần khởi tạo instance của lớp cha hoàn tất trước phần constructor của lớp cha. |
| 8–10 | Field instance, block instance, rồi constructor của `Child` | Chỉ sau khi constructor lớp cha hoàn tất mới đến phần khởi tạo instance và constructor của lớp con. |

Các số trong thông báo là nhãn để dễ đối chiếu, không phải số thứ tự do JVM tự sinh. Dấu vết được in bởi các câu lệnh nằm trong chương trình.

### Vì sao lần tạo đối tượng thứ hai không in các dòng 1–4?

Các static initializer đã chạy trong lần khởi tạo lớp đầu tiên. Lệnh `new Child()` thứ hai vẫn khởi tạo một đối tượng mới, vì vậy các field initializer và instance initializer block của cả `Parent` lẫn `Child` tiếp tục chạy. Nhưng lớp đã được khởi tạo rồi, nên các static initializer không chạy lại.

### Vì sao constructor của lớp cha xuất hiện trước initializer của lớp con?

Constructor lớp con phải gọi constructor lớp cha. Trong quá trình đó, Java khởi tạo phần instance của lớp cha và thực thi constructor lớp cha trước. Khi constructor lớp cha trả về, Java tiếp tục các field initializer và instance initializer block của lớp con, rồi mới chạy phần thân constructor lớp con.

## 5. Quy trình tự giải bài trace

Khi gặp đề yêu cầu dự đoán output về thứ tự khởi tạo, hãy làm theo quy trình sau:

1. **Khoanh vùng lớp được sử dụng đầu tiên.** Xác định hành động nào kích hoạt khởi tạo lớp, ví dụ `new Child()` hoặc gọi một phương thức static.
2. **Liệt kê các lớp theo quan hệ kế thừa.** Ghi lớp cha trước, lớp con sau.
3. **Với từng lớp, quét static từ trên xuống.** Ghi mỗi static field initializer và static block đúng thứ tự xuất hiện.
4. **Theo dõi một đối tượng.** Bắt đầu từ phần khởi tạo instance của lớp cha; trong mỗi lớp, quét field initializer và instance block theo thứ tự văn bản, rồi ghi constructor body.
5. **Đánh dấu các dấu vết chỉ xảy ra một lần.** Static initializer thuộc về lần khởi tạo lớp; instance initializer và constructor thuộc về mỗi lần tạo đối tượng.
6. **Đối chiếu output theo từng dòng.** Không tự sắp xếp lại các dòng theo ý nghĩa của tên biến hay theo vị trí của `new`; thứ tự phải được suy ra từ quy tắc Java và mã nguồn.

Một bảng nháp có thể gồm ba cột: số dòng, câu lệnh phát sinh dấu vết và lý do nó chạy ở thời điểm đó. Cách này đặc biệt hữu ích khi có nhiều lớp cha, nhiều initializer hoặc nhiều lần tạo đối tượng.

## 6. Những nhầm lẫn thường gặp

- **Nghĩ static initializer chạy mỗi lần tạo object:** sai; chúng chạy khi lớp được khởi tạo, không chạy lại cho mỗi instance.
- **Cho rằng tất cả static của lớp con chạy trước static của lớp cha:** sai; lớp cha được khởi tạo trước lớp con.
- **Gộp field initializer và initializer block thành hai nhóm riêng:** sai; trong cùng một lớp, hai loại này đan xen theo đúng thứ tự khai báo trong mã nguồn.
- **Đưa constructor lớp con lên trước constructor lớp cha:** sai; lời gọi constructor lớp cha hoàn tất trước khi phần thân còn lại của constructor lớp con thực thi.
- **Đồng nhất nạp lớp với khởi tạo lớp:** hai bước khác nhau. Khi dự đoán output, cần xác định thời điểm khởi tạo lớp thực sự được kích hoạt.
- **Quên rằng mỗi lần `new` tạo trạng thái instance mới:** các field instance được khởi tạo lại cho từng đối tượng, kể cả khi static state vẫn giữ nguyên.
- **Đọc số nhãn như thể đó là output tự động:** các số trong ví dụ được viết trong chuỗi thông báo. Nếu đổi mã nguồn, phải dự đoán theo câu lệnh thực tế.

## 7. Mở rộng khi dấu vết phức tạp hơn

Nếu constructor dùng `this(...)` để gọi một constructor khác trong cùng lớp, hãy theo chuỗi lời gọi cho đến constructor thực hiện lời gọi `super(...)`. Phần khởi tạo instance của đối tượng chỉ chạy một lần trong chuỗi constructor đó; không cộng thêm một lượt field initializer cho mỗi constructor được gọi qua `this(...)`.

Nếu static initializer gọi phương thức khác hoặc tạo một đối tượng khác, hãy lần theo lời gọi lồng nhau đúng tại vị trí đó. Không chuyển dấu vết của lời gọi lồng nhau xuống cuối bảng: nó xuất hiện ngay khi câu lệnh gọi được thực thi. Cũng cần lưu ý rằng một lỗi trong quá trình khởi tạo lớp có thể làm lần khởi tạo thất bại; các lần sử dụng sau có thể nhận lỗi khởi tạo lớp thay vì chạy lại initializer bình thường.

Để tự kiểm tra, hãy thay đổi vị trí một static block hoặc instance block, thêm một dòng `new Child()`, rồi dự đoán output trước khi chạy lại. Nếu output khác dự đoán, đối chiếu từng dòng với thứ tự khai báo và chuỗi gọi constructor thay vì chỉ xem kết quả cuối cùng.