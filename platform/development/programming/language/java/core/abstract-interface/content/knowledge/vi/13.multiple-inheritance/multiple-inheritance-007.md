# Xung đột giữa default method và abstract method độc lập trong Java

Một default method có body không tự động thỏa một khai báo abstract override-equivalent từ interface độc lập. Cả class kết hợp lẫn interface con kết hợp hai nguồn này cần giải quyết rõ ràng.

## Class kết hợp hai interface

~~~java
interface DefaultTask {
    default String run() { return "default"; }
}
interface RequiredTask {
    String run();
}
// Không hợp lệ nếu không override:
// class BrokenTask implements DefaultTask, RequiredTask {}

final class Task implements DefaultTask, RequiredTask {
    @Override
    public String run() {
        return DefaultTask.super.run() + " + verified";
    }
}
public class Main {
    public static void main(String[] args) {
        System.out.println(new Task().run());
    }
}
~~~

Đầu ra:

~~~text
default + verified
~~~

Task.run() cung cấp implementation rõ ràng và delegate có chủ đích tới default. Nếu bỏ override, compiler báo class chưa triển khai method abstract của RequiredTask.

## Interface con kết hợp hai interface

~~~java
interface DefaultTask {
    default String run() { return "default"; }
}
interface RequiredTask {
    String run();
}
interface Combined extends DefaultTask, RequiredTask {
    @Override
    default String run() {
        return DefaultTask.super.run() + " via Combined";
    }
}
final class Worker implements Combined {}
~~~

Combined giải quyết xung đột ở cấp interface. Nếu nó khai báo run() abstract thay vì default, class concrete phải tự triển khai.

| Nguồn method | Kết quả |
| --- | --- |
| Hai abstract method độc lập, tương thích | Một implementation có thể đáp ứng cả hai |
| Một default và một abstract từ interface độc lập | Cần khai báo giải quyết rõ ràng |
| Hai default độc lập | Cần giải quyết xung đột default |
| Interface con override method của interface cha | Áp dụng quy tắc override/specificity |
| Superclass có abstract method | Concrete subclass vẫn phải hoàn thiện nghĩa vụ class |

Đừng suy luận chỉ từ việc một method có body. Java xét chữ ký và quan hệ giữa các nguồn; nó không quyết định dựa trên ngữ nghĩa nghiệp vụ của default.

Tham khảo: [JLS §9.4.1.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.4.1.3) và [JLS §8.4.8.4](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.4).

## Tự kiểm tra

Vì sao interface con không thể để trống khi kế thừa default và abstract độc lập? Cách nào tái sử dụng default có chủ đích? Hai abstract method tương thích có luôn gây lỗi?

**Đáp án:** phải redeclare để giải quyết; override rồi gọi DefaultTask.super.run(); không.
