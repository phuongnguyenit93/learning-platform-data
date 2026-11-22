# Khởi tạo interface không mặc nhiên khởi tạo mọi interface cha

Trong Java, **khởi tạo (initialization) một interface con không tự động khởi tạo các interface cha của nó**. Đây là điểm khác biệt quan trọng so với khởi tạo một class: trước khi một class được khởi tạo, JVM sẽ khởi tạo superclass của nó và các superinterface có khai báo phương thức `default`. Quy tắc này giúp tránh chạy khởi tạo của mọi interface chỉ vì một interface khác kế thừa nó.

Để hiểu đúng hành vi, hãy phân biệt việc JVM nạp/kiểm tra kiểu với việc khởi tạo kiểu. Khởi tạo là giai đoạn thực thi các biểu thức khởi tạo biến `static` của kiểu đó. Một interface có thể được dùng làm kiểu cha mà chưa chạy phần khởi tạo của nó.

## 1. Khởi tạo trực tiếp một interface

Một interface thường được khởi tạo khi mã lần đầu chủ động sử dụng một thành viên tĩnh được khai báo trong chính interface đó, chẳng hạn gọi phương thức `static` của interface hoặc đọc một trường `static` không phải hằng số biên dịch. Việc truy cập trường là một điểm cần chú ý: nếu trường được khai báo ở interface cha, việc viết tên interface con ở phía trước không biến trường đó thành trường do interface con khai báo.

Khi một interface con được khởi tạo, JVM **không cần khởi tạo trước tất cả interface cha**. Vì vậy, chỉ khai báo `interface Child extends Parent` không có nghĩa các biểu thức khởi tạo của `Parent` sẽ chạy khi `Child` được khởi tạo.

## 2. Ví dụ Java 17+ có thể biên dịch và chạy

Lưu đoạn mã sau thành `InterfaceInitializationDemo.java`:

```java
public class InterfaceInitializationDemo {
    static class InitLog {
        static String mark(String name) {
            System.out.println("init " + name);
            return name;
        }
    }

    interface Parent {
        String PARENT_VALUE = InitLog.mark("Parent");

        default void inheritedDefault() {
        }
    }

    interface Child extends Parent {
        String CHILD_VALUE = InitLog.mark("Child");
    }

    static class Impl implements Child {
        static {
            System.out.println("init Impl");
        }
    }

    public static void main(String[] args) {
        System.out.println("Access Child.CHILD_VALUE");
        System.out.println(Child.CHILD_VALUE);

        System.out.println("Create Impl");
        new Impl();

        System.out.println("Access Parent.PARENT_VALUE");
        System.out.println(Parent.PARENT_VALUE);
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```text
javac InterfaceInitializationDemo.java
java InterfaceInitializationDemo
```

Đầu ra:

```text
Access Child.CHILD_VALUE
init Child
Child
Create Impl
init Parent
init Impl
Access Parent.PARENT_VALUE
Parent
```

## 3. Giải thích thứ tự khởi tạo

**Bước 1 — đọc `Child.CHILD_VALUE`.** Trường này được khởi tạo bằng lời gọi `InitLog.mark`, nên không phải hằng số biên dịch. Việc đọc nó kích hoạt khởi tạo `Child` và in `init Child`. Dù `Child extends Parent`, biểu thức khởi tạo của `Parent` chưa chạy; việc khởi tạo interface con không tự khởi tạo interface cha.

**Bước 2 — tạo `Impl`.** Trước khi JVM khởi tạo class `Impl`, JVM khởi tạo superclass của nó và các superinterface trong cây kế thừa có khai báo phương thức `default`. `Parent` khai báo `inheritedDefault`, nên `Parent` được khởi tạo trước và in `init Parent`. Sau đó khối `static` của `Impl` chạy, in `init Impl`.

**Bước 3 — đọc `Parent.PARENT_VALUE`.** `Parent` đã được khởi tạo ở bước 2, nên biểu thức `InitLog.mark("Parent")` không chạy lần nữa. Chương trình chỉ in giá trị trường `Parent`.

Ví dụ này thể hiện hai quy tắc khác nhau: khởi tạo một interface không kéo theo việc khởi tạo mọi superinterface; còn khởi tạo một class có thể kéo theo việc khởi tạo các superinterface khai báo phương thức `default` trước khi chạy phần khởi tạo của class đó.

## 4. Quy tắc cần nhớ

| Tình huống | Điều xảy ra |
| --- | --- |
| Đọc trường không phải hằng số biên dịch được khai báo trực tiếp trong `Child` | Có thể kích hoạt khởi tạo `Child`; không tự động khởi tạo mọi interface cha. |
| Gọi phương thức `static` được khai báo trong một interface | Kích hoạt khởi tạo interface khai báo phương thức đó. Phương thức `static` của interface không được kế thừa như phương thức instance. |
| Khởi tạo class `Impl` | JVM khởi tạo superclass và các superinterface khai báo phương thức `default` theo quy tắc khởi tạo class trước khi thực thi khối khởi tạo tĩnh của class. |
| Đọc trường được khai báo ở `Parent` qua tên `Parent` | Nếu trường không phải hằng số biên dịch, việc đọc kích hoạt khởi tạo `Parent` nếu nó chưa được khởi tạo. |
| Đọc hằng số biên dịch như `int LIMIT = 100` được khai báo trong interface | Bản thân việc đọc hằng số không kích hoạt khởi tạo interface. |

Các trường khai báo trong interface mặc nhiên là `public static final`. Tuy vậy, không phải trường `final` nào cũng là hằng số biên dịch. Trường kiểu nguyên thủy hoặc `String` được gán bằng biểu thức hằng mới là constant variable theo quy tắc của Java. Ví dụ `String VALUE = InitLog.mark("Child")` không phải biểu thức hằng, nên việc đọc trường sẽ kích hoạt khởi tạo interface khai báo nó.

Nếu một trường do `Parent` khai báo được tham chiếu qua tên `Child`, hãy nhớ rằng trường đó vẫn thuộc về `Parent`. Khi trường không phải hằng số biên dịch, thao tác truy cập có thể kích hoạt khởi tạo `Parent`; không nên suy luận chỉ từ tên đứng trước dấu chấm.

## 5. Lỗi hiểu thường gặp

- **Cho rằng `extends` đồng nghĩa với khởi tạo cha:** quan hệ kế thừa xác định kiểu và thành viên, nhưng khởi tạo interface có quy tắc riêng. Khởi tạo interface con không mặc nhiên khởi tạo các interface cha.
- **Nhầm quy tắc của class với interface:** khi khởi tạo class, JVM có xử lý đặc biệt đối với superinterface khai báo phương thức `default`. Không áp dụng quy tắc đó như thể mỗi lần khởi tạo một interface con cũng phải khởi tạo mọi cha.
- **Cho rằng mọi trường `static final` đều không kích hoạt khởi tạo:** điều đó chỉ đúng với constant variable được Java xác định là hằng số biên dịch. Giá trị lấy từ lời gọi phương thức hoặc phép tính không phải biểu thức hằng có thể kích hoạt khởi tạo.
- **Bỏ qua interface khai báo thực sự trường:** tên interface dùng trong biểu thức truy cập không nhất thiết là nơi khai báo trường. Hãy xác định thành viên được khai báo ở interface nào để hiểu interface nào sẽ được khởi tạo.

## 6. Cách áp dụng khi debug

Khi thấy log khởi tạo tĩnh xuất hiện theo thứ tự bất ngờ, hãy xác định thao tác đầu tiên gây khởi tạo: đọc trường nào, gọi phương thức `static` nào, hay khởi tạo class nào. Sau đó kiểm tra trường đó có phải constant variable không và các interface nào trong cây kế thừa khai báo phương thức `default`. Không kết luận rằng một interface cha đã được khởi tạo chỉ vì interface con kế thừa nó.

Trong thiết kế thực tế, nên tránh dựa vào side effect phức tạp trong biểu thức khởi tạo trường interface. Nếu cần theo dõi thứ tự, dùng ví dụ nhỏ có log rõ ràng như trên và kiểm tra bằng một chương trình chạy độc lập.