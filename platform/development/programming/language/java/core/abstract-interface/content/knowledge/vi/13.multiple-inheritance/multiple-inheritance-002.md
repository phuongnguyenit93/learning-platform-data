# Kế thừa cùng một khai báo abstract qua nhiều đường trong Java

Hai interface trung gian có thể cùng kế thừa một khai báo abstract từ interface gốc. Hai đường truyền hợp đồng không tạo ra hai nghĩa vụ riêng.

~~~java
interface Task { void run(); }
interface Read extends Task {}
interface Write extends Task {}
interface ReadWrite extends Read, Write {}

final class Worker implements ReadWrite {
    @Override
    public void run() {
        System.out.println("running");
    }
}
~~~

Task.run() là một khai báo abstract được kế thừa qua cả Read và Write. Một method public void run() là đủ để đáp ứng hợp đồng.

## Hai khai báo độc lập cũng có thể tương thích

~~~java
interface Printable { void print(); }
interface Exportable { void print(); }

final class Report implements Printable, Exportable {
    @Override
    public void print() {
        System.out.println("report");
    }
}
~~~

Printable.print() và Exportable.print() là hai khai báo khác nhau, nhưng một method đáp ứng cả hai vì chữ ký tương thích.

| Tình huống | Kết quả |
| --- | --- |
| Cùng khai báo abstract qua hai nhánh | Một implementation |
| Hai khai báo abstract độc lập cùng chữ ký tương thích | Một implementation |
| Cùng tên nhưng tham số khác nhau | Hai overload, xét riêng |
| Cùng chữ ký nhưng return type không tương thích | Lỗi hợp đồng kiểu |

Method abstract thông thường của interface là public. Với các throws khác nhau, implementation không được khai báo checked exception rộng hơn điều mọi hợp đồng cho phép. Với generic, kiểm tra type argument qua từng nhánh; không kế thừa tùy tiện cả Source&lt;String&gt; và Source&lt;Integer&gt;.

Không viết hai method giống nhau trong một class để “phục vụ” từng interface. Đổi tham số để tạo overload cũng không triển khai method abstract ban đầu. Dùng @Override để compiler phát hiện sai chữ ký.

## Tự kiểm tra

Hai interface khai báo void execute() cần mấy method? Hai khai báo execute(String) và execute(int) có thể hợp nhất không? Vì sao implementation cần public?

**Đáp án:** Một; không, đây là hai overload; vì method abstract của interface là public.
