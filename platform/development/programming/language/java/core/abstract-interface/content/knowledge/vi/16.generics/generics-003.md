# Phương thức generic và khác biệt với kiểu chứa generic trong Java

## 1. Hai nơi khai báo tham số kiểu

Một **generic type** khai báo tham số kiểu sau tên class hoặc interface. Một **generic method** khai báo tham số kiểu riêng ngay trong chữ ký phương thức, trước kiểu trả về.

~~~java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    <U> U echo(U input) {
        return input;
    }
}

class Utility {
    static <T> T identity(T input) {
        return input;
    }
}
~~~

Trong **`Box<T>`**, T thuộc phạm vi của class; get() sử dụng T nhưng bản thân get() không phải generic method. Phương thức **echo** khai báo U riêng, vì vậy cùng một `Box<String>` vẫn có thể gọi echo(42) và nhận Integer. **Utility.identity** cho thấy generic method không yêu cầu class chứa phải là generic.

## 2. Cú pháp và suy luận kiểu

Dạng tổng quát:

~~~java
static <T> T first(List<T> values) {
    return values.get(0);
}
~~~

Phần **`<T>`** khai báo type parameter của phương thức; T tiếp theo là kiểu trả về; `List<T>` liên kết kiểu phần tử đầu vào với kiểu kết quả. Khi gọi first(List.of("red", "blue")), compiler suy luận T là String, nên kết quả có kiểu String mà không cần cast.

Có thể chỉ rõ type argument bằng type witness khi muốn làm ý định rõ hơn:

~~~java
String inferred = first(List.of("red", "blue"));
String explicit = Utility.<String>identity("Java");
~~~

Thông thường compiler tự suy luận từ đối số và ngữ cảnh. Type witness là tùy chọn khi suy luận đã đủ rõ; nó không làm cho những kiểu không tương thích trở nên hợp lệ.

## 3. Ví dụ hoàn chỉnh: nhiều generic method trong một class thường

Lưu mã vào **GenericMethodDemo.java**:

~~~java
import java.util.List;

final class TextTools {
    private TextTools() {
    }

    static <T> T first(List<T> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("values must not be empty");
        }
        return values.get(0);
    }

    static <T> void showPair(T left, T right) {
        System.out.println(left + " | " + right);
    }

    static <T extends Number> double sum(List<T> values) {
        double total = 0.0;
        for (T value : values) {
            total += value.doubleValue();
        }
        return total;
    }
}

public class GenericMethodDemo {
    public static void main(String[] args) {
        TextTools.showPair("Java", "17");
        TextTools.showPair(10, 20);

        String first = TextTools.first(List.of("alpha", "beta"));
        System.out.println(first);
        System.out.println(TextTools.sum(List.of(1, 2, 3)));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 GenericMethodDemo.java
java GenericMethodDemo
~~~

Kết quả:

~~~text
Java | 17
10 | 20
alpha
6.0
~~~

Lần gọi showPair đầu tiên suy luận T là String; lần gọi thứ hai suy luận T là Integer. Mỗi lời gọi có thể suy luận một kiểu khác. Với sum, giới hạn T extends Number cho phép gọi doubleValue() an toàn vì compiler biết mọi T hợp lệ đều là Number hoặc kiểu con của Number.

## 4. Khi generic class và generic method cùng tồn tại

~~~java
final class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    void set(T value) {
        this.value = value;
    }

    <U> U echo(U input) {
        return input;
    }

    static <U> U identity(U input) {
        return input;
    }
}
~~~

**T** thuộc về `Box<T>`; get() và set() dùng kiểu của hộp. **U** thuộc về echo(), độc lập với T của đối tượng. Vì vậy, `Box<String>` có thể lưu String nhưng vẫn gọi echo(42). Phương thức static identity cũng khai báo U riêng, nên không phụ thuộc vào một `Box<T>` cụ thể.

Ngược lại, một static member không thể dùng trực tiếp T của class như thể đã có một instance xác định T. Nếu cần một static method tổng quát, hãy khai báo type parameter riêng, như **`static <U> U identity(U input)`**.

## 5. Nhiều type parameter và giới hạn

Một phương thức có thể liên kết nhiều tham số kiểu để bảo toàn quan hệ giữa đầu vào và đầu ra:

~~~java
static <S, T> T convert(S source, java.util.function.Function<S, T> converter) {
    return converter.apply(source);
}
~~~

Ở đây S là kiểu nguồn, T là kiểu kết quả. Khi truyền String và hàm chuyển thành Integer, compiler có thể giữ quan hệ đó ở chữ ký. Nếu phương thức chỉ cần một kiểu đã biết từ class, không cần khai báo lại một type parameter riêng.

Có thể thêm giới hạn cho phương thức:

~~~java
static <T extends Number> double asDouble(T value) {
    return value.doubleValue();
}
~~~

Không có giới hạn, compiler không thể cho phép gọi doubleValue() trên một T tùy ý. Nếu có nhiều giới hạn, cú pháp và thứ tự class/interface được giải thích ở bài về type bounds và intersection type.

## 6. Generic method khác wildcard như thế nào?

~~~java
static <T> T first(List<T> values) {
    return values.get(0);
}

static void printAll(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
~~~

first dùng T có tên để liên kết kiểu phần tử với kiểu trả về: truyền `List<String>` thì kết quả là String. printAll chỉ cần duyệt danh sách, không cần biết kiểu phần tử, nên List<?> diễn đạt ý định đơn giản hơn. Wildcard có giới hạn như ? extends Number thường hữu ích khi đọc nhiều kiểu số; ? super Integer phù hợp khi cần ghi Integer vào danh sách.

Hãy dùng type parameter có tên khi nhiều vị trí phải chia sẻ cùng một kiểu hoặc kiểu trả về cần giữ mối quan hệ với đầu vào. Dùng wildcard khi kiểu phần tử cụ thể không quan trọng đối với thao tác cần thực hiện.

## 7. Lỗi thường gặp

- **Quên khai báo type parameter:** trong class không generic, T chỉ hợp lệ nếu phương thức khai báo `<T>` hoặc một phạm vi khác đã khai báo T.
- **Nhầm method dùng T của class với generic method:** T get() trong `Box<T>` không có type parameter riêng.
- **Dùng T của class trong static context:** static method cần khai báo type parameter riêng nếu muốn tổng quát.
- **Cho rằng mọi đối số trong cùng lời gọi có thể tùy ý khác kiểu:** các vị trí cùng dùng T phải thỏa cùng ràng buộc suy luận.
- **Thêm generic mà không tạo được quan hệ kiểu hữu ích:** nếu type parameter không giúp liên kết tham số, kết quả hoặc giới hạn hành vi, chữ ký đơn giản hơn có thể rõ ràng hơn.

Type erasure cũng ảnh hưởng đến những overload chỉ khác type argument; nội dung đó thuộc bài về name clash. Bài này tập trung vào phạm vi type parameter, suy luận kiểu và cách giữ quan hệ giữa đầu vào và kết quả.