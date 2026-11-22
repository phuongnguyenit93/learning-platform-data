# Bài toán hình thoi trong hệ phân cấp interface của Java

Bài toán hình thoi xuất hiện khi một kiểu nhận hợp đồng hoặc hành vi qua nhiều nhánh interface. Java không cho class kế thừa trực tiếp nhiều class, nhưng interface có thể mở rộng nhiều interface và class có thể triển khai nhiều interface.

~~~text
Root -> Left -> Child
Root -> Right -> Child
~~~

| Hệ phân cấp | Kết quả | Lý do |
| --- | --- | --- |
| Hai nhánh cùng kế thừa một abstract method từ gốc | Thường hợp lệ | Một implementation tương thích đáp ứng hợp đồng chung. |
| Hai nhánh cùng kế thừa một default từ gốc, không override | Hợp lệ | Chỉ có một default implementation. |
| Hai interface độc lập cung cấp default cùng chữ ký | Cần giải quyết | Java không tự chọn giữa hai body ngang hàng. |

~~~java
interface Root {
    void run();
    default String label() { return "root"; }
}
interface Read extends Root {}
interface Write extends Root {}
interface ReadWrite extends Read, Write {}

final class Worker implements ReadWrite {
    @Override
    public void run() {
        System.out.println("run once");
    }
}
public class Main {
    public static void main(String[] args) {
        Worker worker = new Worker();
        Root root = worker;
        ReadWrite combined = worker;
        root.run();
        combined.run();
        System.out.println(combined.label());
    }
}
~~~

Đầu ra:

~~~text
run once
run once
root
~~~

Worker.run() là một implementation được gọi hai lần qua hai kiểu tham chiếu. label() được kế thừa từ Root qua cả hai nhánh mà không tạo xung đột.

Khi phân tích, tìm nơi khai báo thực tế của từng method; đối chiếu tên, tham số, return type, visibility và throws; kiểm tra superclass; sau đó quyết định có cần override ở class hoặc interface con hay không.

Field trong interface là hằng public static final; interface không có instance field để sao chép qua các nhánh.

## Tự kiểm tra

Hai nhánh cùng kế thừa một abstract method cần mấy implementation? Hai nhánh cùng kế thừa một default từ gốc có tự xung đột không? Hai interface độc lập có default cùng chữ ký cần làm gì?

**Đáp án:** Một; không; cần override hoặc khai báo giải quyết phù hợp.
