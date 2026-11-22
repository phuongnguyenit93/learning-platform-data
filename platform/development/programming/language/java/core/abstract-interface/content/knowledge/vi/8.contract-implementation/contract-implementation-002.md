# Phương thức thực thi interface phải public trong Java

Phương thức instance abstract thông thường trong Java interface có mức truy cập **public**, ngay cả khi khai báo không viết từ khóa này. Vì vậy, lớp cung cấp phần thân để đáp ứng phương thức đó phải giữ mức truy cập public. Java không cho phép implementation thu hẹp quyền truy cập của hợp đồng mà người gọi đang sử dụng.

## 1. Ví dụ đúng và sai

Lưu chương trình sau vào **PublicContractDemo.java**:

~~~java
public class PublicContractDemo {
    interface Task {
        void run(); // Ngầm hiểu là public abstract.
    }

    static final class PrintTask implements Task {
        @Override
        public void run() {
            System.out.println("running");
        }
    }

    public static void main(String[] args) {
        Task task = new PrintTask();
        task.run();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac PublicContractDemo.java
java PublicContractDemo
~~~

Kết quả:

~~~text
running
~~~

Nếu bỏ từ khóa **public** khỏi **PrintTask.run()**, phương thức trong class trở thành package-private. Đoạn sau được cố ý viết sai:

~~~java
interface Task {
    void run();
}

class InvalidTask implements Task {
    @Override
    void run() {
        System.out.println("running");
    }
}
~~~

Compiler báo rằng phương thức trong **InvalidTask** đang cố triển khai phương thức public với quyền truy cập yếu hơn. Đổi thành **protected** hoặc **private** cũng không hợp lệ. Annotation **@Override** giúp kiểm tra quan hệ phương thức nhưng không tự thêm từ khóa public.

## 2. Vì sao phải giữ public?

Interface là một kiểu mà code gọi có thể phụ thuộc vào mà không cần biết lớp triển khai cụ thể. Khi biến có kiểu **Task**, người gọi có quyền gọi **run()** theo hợp đồng public. Nếu một implementation có thể hạ phương thức xuống package-private hoặc protected, cùng lời gọi sẽ phụ thuộc vào package hay quan hệ kế thừa của lớp cụ thể, làm hỏng khả năng thay thế mà interface hứa hẹn.

Trong class, phương thức không ghi modifier mặc định là package-private. Java không tự suy ra rằng bạn muốn dùng public chỉ vì tên và tham số trùng với interface. Vì thế hãy ghi rõ **public** khi triển khai hợp đồng interface.

## 3. Phân biệt các loại phương thức trong interface

| Dạng khai báo | Vai trò | Lớp triển khai có cần tự viết phương thức không? |
| --- | --- | --- |
| Phương thức abstract thông thường, ví dụ **void run();** | Public abstract, không có thân | Có, nếu chưa kế thừa implementation hợp lệ; phần thân phải public |
| Phương thức **default** có thân | Hành vi instance mặc định, cũng là public | Không bắt buộc; nếu override thì vẫn phải public |
| Phương thức **static** có thân | Thuộc interface, được gọi qua tên interface | Không; static không override phương thức instance |
| Phương thức **private** có thân | Helper nội bộ bên trong interface | Không; nó không phải hợp đồng cho lớp triển khai |

Từ khóa **private** trong bảng chỉ dùng cho helper có thân trong interface. Nó không cho phép một lớp triển khai phương thức abstract public bằng một phương thức private.

## 4. Phương thức lớp cha có đáp ứng được không?

Một lớp concrete có thể đáp ứng interface bằng phương thức public, concrete và tương thích được kế thừa từ superclass. Nó không bắt buộc phải khai báo lại phương thức chỉ để lặp lại cùng phần thân. Tuy nhiên, phương thức protected hoặc package-private từ lớp cha không tự trở thành public khi lớp con thêm **implements**.

Ví dụ: nếu **BaseTask** có **public void run()**, lớp **TaskImpl extends BaseTask implements Task** có thể dùng phương thức đó. Nếu **BaseTask** chỉ có **protected void run()**, lớp con phải cung cấp một implementation public hợp lệ hoặc thiết kế lại quan hệ lớp. Quy tắc về phương thức kế thừa được phân tích riêng trong bài kế tiếp của chương.

Một abstract class cũng phải tuân thủ quy tắc này nếu nó **tự khai báo lại** phương thức interface. Nó có thể để phương thức chưa được khai báo và trì hoãn nghĩa vụ vì vẫn abstract, nhưng không thể viết **protected abstract void run()** để thay thế một phương thức interface public.

## 5. Lỗi thường gặp

- Quên **public** vì cho rằng Java sẽ tự kế thừa modifier từ interface.
- Dùng **protected** với lý do chỉ các lớp con cần gọi phương thức. Nếu đó là phương thức public của interface, hãy giữ public và chuyển logic hỗ trợ riêng sang một helper protected/private khác.
- Cho rằng mọi phương thức interface đều phải tự viết. Default method có thân, và phương thức public tương thích từ superclass cũng có thể đáp ứng hợp đồng.
- Nhầm helper **private** trong interface với phương thức abstract mà lớp triển khai phải cung cấp.
- Chỉ nhìn tên phương thức. Khác kiểu tham số vẫn là một chữ ký khác; public đúng nhưng chữ ký sai vẫn không đáp ứng hợp đồng.

## 6. Tự kiểm tra

**Câu 1.** Vì sao khai báo **void save();** trong interface vẫn yêu cầu phương thức triển khai public?

**Đáp án:** các phương thức instance abstract thông thường trong interface ngầm định là public abstract.

**Câu 2.** Abstract class có thể để **save()** chưa được triển khai không?

**Đáp án:** có, nếu lớp vẫn abstract. Nhưng nếu lớp đó tự khai báo lại phương thức, nó không được thu hẹp quyền truy cập của hợp đồng public.

**Câu 3.** Nếu interface có một default method public, lớp con có thể override bằng protected không?

**Đáp án:** không. Khi override, phương thức vẫn không được giảm quyền truy cập.

**Ghi nhớ:** phần thân triển khai phương thức instance public của interface phải public. Hãy phân biệt modifier của phương thức với việc phương thức có cần được viết lại hay không.