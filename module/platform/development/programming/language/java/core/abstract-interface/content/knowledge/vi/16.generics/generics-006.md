# Tính bất biến của generic và wildcard tại ranh giới API trong Java

## 1. Vì sao generic là bất biến?

Nếu Integer là subtype của Number, một biến Number có thể tham chiếu đến Integer. Nhưng quan hệ đó không mở rộng thành List\<Integer> là subtype của List\<Number>:

~~~java
Number number = Integer.valueOf(10);
List<Integer> integers = new ArrayList<>();

// Không biên dịch:
// List<Number> numbers = integers;
~~~

Nếu phép gán trên hợp lệ, người nhận có thể thêm Double vào danh sách vốn chỉ dành cho Integer. Java từ chối phép gán để bảo toàn type safety ở thời điểm biên dịch.

## 2. Chọn wildcard theo thao tác

| Kiểu tham số | Đọc an toàn thành | Thêm giá trị khác null | Dùng khi |
| --- | --- | --- | --- |
| List\<T> | T | Có thể thêm T | Cần đọc và ghi cùng kiểu đã biết |
| List<?> | Object | Không thêm giá trị tùy ý | Chỉ duyệt/in phần tử |
| List<? extends Number> | Number | Không thêm Number tùy ý | Đọc các kiểu số |
| List<? super Integer> | Object | Có thể thêm Integer | Ghi Integer vào danh sách kiểu đó hoặc kiểu cha |

### Upper bound: Producer Extends

~~~java
static double sum(List<? extends Number> values) {
    double total = 0.0;
    for (Number value : values) {
        total += value.doubleValue();
    }
    return total;
}
~~~

Có thể truyền List\<Integer>, List\<Double> hoặc List\<Number>. Khi đọc, mỗi phần tử đều dùng được như Number. Không thể thêm Integer tùy ý vì danh sách thực tế có thể là List\<Double>.

### Lower bound: Consumer Super

~~~java
static void addDefaults(List<? super Integer> destination) {
    destination.add(10);
    destination.add(20);
}
~~~

Có thể truyền List\<Integer>, List\<Number> hoặc List\<Object>. Thêm Integer là an toàn; khi đọc, kiểu chung an toàn nhất là Object vì danh sách thực tế có thể chứa những kiểu khác.

**PECS** là mẹo ghi nhớ: Producer Extends cho nguồn cung cấp dữ liệu; Consumer Super cho đích nhận dữ liệu. Đây là hướng dẫn thiết kế, không phải luật bắt buộc cho mọi chữ ký.

## 3. Ví dụ hoàn chỉnh

~~~java
import java.util.ArrayList;
import java.util.List;

public class GenericVarianceDemo {
    static double sum(List<? extends Number> values) {
        double total = 0.0;
        for (Number value : values) {
            total += value.doubleValue();
        }
        return total;
    }

    static void addIntegers(List<? super Integer> destination, int... values) {
        for (int value : values) {
            destination.add(value);
        }
    }

    static <T> void copyAll(
            List<? super T> destination,
            List<? extends T> source) {
        for (T value : source) {
            destination.add(value);
        }
    }

    static void printAll(List<?> values) {
        for (Object value : values) {
            System.out.println(value);
        }
    }

    static <T> void swap(List<T> values, int left, int right) {
        T temporary = values.get(left);
        values.set(left, values.get(right));
        values.set(right, temporary);
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>(List.of(1, 2, 3));
        System.out.println(sum(integers));

        List<Number> numbers = new ArrayList<>();
        numbers.add(1.5);
        addIntegers(numbers, 7, 8);
        System.out.println(numbers);

        copyAll(numbers, integers);
        System.out.println(numbers);

        swap(integers, 0, 2);
        printAll(integers);
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac GenericVarianceDemo.java
java GenericVarianceDemo
~~~

Kết quả:

~~~text
6.0
[1.5, 7, 8]
[1.5, 7, 8, 1, 2, 3]
3
2
1
~~~

**copyAll** dùng T để liên kết kiểu nguồn với kiểu đích, đồng thời dùng wildcard để cho phép nguồn sản xuất T và đích tiêu thụ T. **swap** dùng List\<T> vì nó phải đọc và ghi lại cùng kiểu phần tử.

## 4. Khi nào dùng T thay vì wildcard?

~~~java
static <T> T first(List<T> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("values must not be empty");
    }
    return values.get(0);
}

static Object firstUnknown(List<?> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("values must not be empty");
    }
    return values.get(0);
}
~~~

Với List\<String>, phương thức đầu trả về String; phương thức thứ hai chỉ trả về Object. Dùng T có tên khi cần giữ quan hệ kiểu giữa tham số, nhiều vị trí hoặc kết quả. Dùng List<?> khi không cần biết kiểu phần tử.

Wildcard không thay đổi quan hệ subtype giữa các kiểu generic cụ thể. Nó chỉ cho phép biến hoặc tham số có wildcard nhận những type argument phù hợp. Type erasure, raw type và unchecked cast là các chủ đề liên quan nhưng có quy tắc riêng.

## 5. Lỗi thường gặp

- Gán List\<Child> cho List\<Parent> chỉ vì Child extends Parent.
- Dùng ? extends T rồi cố thêm một giá trị T tùy ý.
- Dùng ? super T rồi giả định phần tử đọc ra là T thay vì Object.
- Thêm wildcard vào mọi chữ ký dù List\<T> đã biểu đạt đúng quan hệ đọc/ghi.
- Quên rằng wildcard không bảo đảm collection có thể thay đổi; danh sách bất biến vẫn có thể ném UnsupportedOperationException.

Thiết kế chữ ký theo thao tác thực tế. Với nguồn đọc, cân nhắc ? extends T; với đích ghi, cân nhắc ? super T; khi cần đọc và ghi cùng kiểu đã biết, List\<T> thường rõ ràng hơn.