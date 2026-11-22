# Nhiều giới hạn kiểu và intersection type trong Java Generics

## 1. Multiple bounds biểu đạt điều kiện “tất cả”

Một thuật toán có thể cần một đối tượng đáp ứng nhiều hợp đồng cùng lúc: có ID, có tên và có giá trị đo được. Java cho phép khai báo nhiều giới hạn cho cùng một type parameter bằng dấu **&**:

~~~java
<T extends Number>
<T extends Comparable<T>>
<T extends Number & Comparable<T> & java.io.Serializable>
~~~

Một kiểu hợp lệ phải đáp ứng mọi bound. Nếu có class bound, nó phải đứng đầu và chỉ có tối đa một class bound; các bound sau là interface. Khi không có class bound, có thể liệt kê nhiều interface.

## 2. Ví dụ hoàn chỉnh

~~~java
interface Named {
    String name();
}

interface Measurable {
    double measure();
}

abstract class RecordBase {
    private final String id;

    protected RecordBase(String id) {
        this.id = id;
    }

    public String id() {
        return id;
    }
}

final class MetricRecord extends RecordBase
        implements Named, Measurable, Comparable<MetricRecord> {
    private final String name;
    private final double score;

    MetricRecord(String id, String name, double score) {
        super(id);
        this.name = name;
        this.score = score;
    }

    @Override
    public String name() {
        return name;
    }

    @Override
    public double measure() {
        return score;
    }

    @Override
    public int compareTo(MetricRecord other) {
        return Double.compare(score, other.score);
    }
}

public class IntersectionTypeDemo {
    static <T extends RecordBase & Named & Measurable>
    String describe(T item) {
        return item.id() + ": " + item.name()
                + " (" + item.measure() + ")";
    }

    static <T extends RecordBase & Named & Measurable & Comparable<T>>
    T chooseLarger(T left, T right) {
        return left.compareTo(right) >= 0 ? left : right;
    }

    public static void main(String[] args) {
        MetricRecord alpha = new MetricRecord("alpha", "Alpha", 7.0);
        MetricRecord beta = new MetricRecord("beta", "Beta", 12.0);

        System.out.println(describe(alpha));
        System.out.println("winner=" + chooseLarger(alpha, beta).name());

        Object unknown = alpha;
        System.out.println("intersection="
                + ((Named & Measurable) unknown).name()
                + "/" + ((Named & Measurable) unknown).measure());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac IntersectionTypeDemo.java
java IntersectionTypeDemo
~~~

Kết quả:

~~~text
alpha: Alpha (7.0)
winner=Beta
intersection=Alpha/7.0
~~~

**describe** cần lớp nền RecordBase cùng hai interface; compiler cho phép gọi id(), name() và measure() trực tiếp. **chooseLarger** bổ sung Comparable\<T>, nên có thể so sánh hai đối tượng cùng kiểu và trả về T. MetricRecord đáp ứng toàn bộ bound.

## 3. Bound và intersection cast khác nhau

Bound như **T extends RecordBase & Named & Measurable** ràng buộc kiểu đầu vào ở thời điểm biên dịch. Nếu kiểu không đáp ứng mọi bound, lời gọi bị từ chối.

Intersection cast như **(Named & Measurable) unknown** kiểm tra đối tượng thực tế khi chạy. Nếu object không thực hiện cả hai interface, cast có thể ném ClassCastException. Dùng cast khi cần kiểm tra một giá trị có kiểu tĩnh rộng; nếu API luôn cần nhiều khả năng, hãy thể hiện chúng trong bound để phát hiện lỗi sớm hơn.

## 4. Lỗi thường gặp

- Đặt interface trước class bound, ví dụ **\<T extends Named & RecordBase>** khi RecordBase là class.
- Khai báo hai class bound cho một type parameter.
- Dùng dấu phẩy thay dấu &: dấu phẩy ngăn cách các type parameter khác nhau, còn & kết hợp nhiều bound của cùng một parameter.
- Cho rằng chỉ cần đáp ứng một bound: **T extends Named & Measurable** yêu cầu cả hai.
- Thêm bound không phục vụ thao tác thật sự của thuật toán, khiến API loại bỏ những kiểu có thể dùng được.

Hãy xác định các phương thức thuật toán cần gọi, ánh xạ từng phương thức tới class/interface cung cấp hợp đồng, rồi khai báo ít bound nhất nhưng vẫn đủ.