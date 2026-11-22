# Ưu tiên default method của interface cụ thể hơn trong Java

Khi interface con override default method từ interface cha, khai báo ở interface con cụ thể hơn được ưu tiên. “Cụ thể hơn” phụ thuộc vào quan hệ extends, không phụ thuộc thứ tự viết tên trong implements.

~~~java
interface BaseFormatter {
    default String format() { return "base"; }
}
interface DetailedFormatter extends BaseFormatter {
    @Override
    default String format() { return "detailed"; }
}
final class Report implements DetailedFormatter {}

public class Main {
    public static void main(String[] args) {
        Report report = new Report();
        BaseFormatter view = report;
        System.out.println(report.format());
        System.out.println(view.format());
    }
}
~~~

Đầu ra là detailed hai lần. Cả hai lời gọi thông thường dùng default cụ thể hơn, kể cả khi biến tham chiếu có kiểu cha.

## Hình thoi có một nhánh cụ thể hơn

~~~java
interface Root { default String message() { return "root"; } }
interface Left extends Root {}
interface Right extends Root {
    @Override
    default String message() { return "right"; }
}
final class Result implements Left, Right {}
~~~

Result nhận default từ Right: nhánh Right override default gốc, còn Left chỉ kế thừa nó. Nếu Left và Right tự khai báo default riêng mà không có quan hệ subtype, xem bài về xung đột giữa hai default không liên quan.

Interface con cũng có thể override default bằng khai báo abstract để buộc class concrete tự cung cấp body.

## Ghi nhớ

- Quan hệ extends xác định interface nào cụ thể hơn.
- Đảo thứ tự implements A, B thành implements B, A không đổi kết quả.
- Hai default độc lập cần được giải quyết tường minh.
- Method concrete từ superclass có quy tắc ưu tiên riêng.
- InterfaceName.super.method() có giới hạn; không dùng để bỏ qua tùy ý một interface con cụ thể hơn.

## Tự kiểm tra

Child extends Parent và override default run(). Lớp chỉ implements Child dùng default nào? Nếu interface con khai báo lại run() abstract thì class concrete cần làm gì?

**Đáp án:** default của Child; class concrete phải cung cấp implementation.
