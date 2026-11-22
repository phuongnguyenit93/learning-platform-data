# Checked exception khi ghi đè phương thức trong Java

Checked exception là một phần của hợp đồng được kiểm tra lúc biên dịch. Khi override hoặc implement phương thức, lớp con không được buộc caller xử lý một checked exception mới hoặc rộng hơn điều mà hợp đồng cha cho phép.

## 1. Quy tắc

Nếu phương thức cha khai báo checked exceptions, phương thức con có thể giữ các loại đó, chọn subtype phù hợp, bỏ bớt loại hoặc không khai báo checked exception. Nếu cha không khai báo checked exception, con không thể thêm một checked exception mới. Unchecked exceptions không chịu giới hạn này; bài kế tiếp nói riêng về hành vi và trách nhiệm của caller.

~~~java
import java.io.FileNotFoundException;
import java.io.IOException;

abstract class DataSource {
    abstract String load(String key) throws IOException;
}

final class CacheSource extends DataSource {
    @Override
    String load(String key) throws FileNotFoundException {
        return "cached:" + key;
    }
}
~~~

FileNotFoundException là subtype của IOException, nên đây là override hợp lệ.

| throws ở cha | throws ở con | Hợp lệ? |
| --- | --- | --- |
| IOException | IOException | Có |
| IOException | FileNotFoundException | Có |
| IOException | Không có throws | Có |
| IOException | Exception | Không: rộng hơn |
| IOException | SQLException | Không: checked type không tương thích |
| Không có checked exception | IOException | Không |
| Không có checked exception | IllegalStateException | Có: unchecked |

Quy tắc xét khai báo throws, không dựa vào việc thân phương thức hiện tại có thực sự ném exception hay không.

## 2. Vì sao không được mở rộng checked exception?

~~~java
import java.io.IOException;

class Parent {
    void read() throws IOException { }
}

class Child extends Parent {
    @Override
    void read() throws Exception { } // Không hợp lệ
}
~~~

Caller dùng biến kiểu Parent có thể đã bắt hoặc khai báo IOException. Nếu Child.read() được phép công bố Exception, lời gọi đa hình có thể phát sinh nhiều loại checked exception mà caller chưa được yêu cầu xử lý. Compiler chặn trường hợp đó.

Tương tự, nếu interface khai báo void run() không có checked exception, implementation không được thêm throws IOException. Nó phải xử lý exception trong thân, chuyển đổi sang một lỗi phù hợp hoặc thay đổi hợp đồng ở nơi có quyền thiết kế API.

## 3. Nghĩa vụ của caller vẫn theo kiểu tĩnh

~~~java
import java.io.IOException;

interface Worker {
    void work() throws IOException;
}

final class LocalWorker implements Worker {
    @Override
    public void work() {
        System.out.println("done");
    }
}

class UseWorker {
    void run() throws IOException {
        Worker polymorphic = new LocalWorker();
        polymorphic.work(); // Xử lý/khai báo IOException theo Worker

        LocalWorker concrete = new LocalWorker();
        concrete.work();    // Không cần IOException theo LocalWorker
    }
}
~~~

Việc LocalWorker.work() không khai báo checked exception không xóa nghĩa vụ tại lời gọi qua biến Worker, vì compiler kiểm tra theo khai báo được nhìn thấy qua kiểu tĩnh.

## 4. Nhiều hợp đồng cùng lúc

Nếu một lớp implement hai interface có cùng phương thức nhưng lần lượt khai báo throws IOException và throws SQLException, một implementation chung phải thỏa **cả hai**. Không thể chỉ chọn hợp đồng thuận tiện hơn; giải pháp thường là xử lý checked exceptions bên trong và không khai báo chúng ở implementation.

Trong chuỗi kế thừa, mỗi override phải tương thích với hợp đồng gần nhất mà nó ghi đè. Nếu GrandParent cho phép Exception, Parent thu hẹp còn IOException, thì Child chỉ có thể thu hẹp tiếp theo quy tắc của Parent; không thể dùng SQLException chỉ vì nó cũng là con của Exception.

## 5. throws không phân biệt overload

Không thể khai báo hai phương thức cùng tên và cùng tham số chỉ khác throws. Danh sách throws không phải thành phần phân biệt chữ ký overload, nhưng được compiler kiểm tra khi một phương thức thực sự override. Constructor cũng không override constructor cha; tuy nhiên, constructor con vẫn phải xử lý checked exception phát sinh từ lời gọi super(...) theo quy tắc thông thường.

Khi gặp lỗi compiler về exception, hãy xác định đúng phương thức bị override, phân loại exception, đối chiếu quan hệ subtype với từng hợp đồng cha/interface và kiểm tra kiểu tĩnh tại vị trí gọi. Đừng xóa @Override để né lỗi: annotation không gây ra giới hạn throws, nó chỉ giúp compiler xác nhận quan hệ override.