# Giới hạn đối với kiểu nguyên thủy và ngoại lệ khai báo

Kiểu trả về đồng biến cho phép phương thức ghi đè trả về kiểu tham chiếu cụ thể hơn. Ví dụ, phương thức cha trả `Number`, phương thức con có thể trả `Integer`.

Quyền thu hẹp này không áp dụng giống nhau cho mọi phần của khai báo phương thức:

- **Kiểu trả về nguyên thủy phải giữ nguyên**, không được đổi chỉ vì có phép chuyển đổi số.
- **Ngoại lệ checked trong `throws` không được mở rộng vượt hợp đồng của phương thức bị ghi đè**.
- Kiểu trả về và danh sách ngoại lệ là hai điều kiện cần kiểm tra riêng.

Hiểu các giới hạn này giúp thiết kế lớp con thay thế được lớp cha: bên gọi nhận được giá trị phù hợp và không bị buộc xử lý thêm một loại lỗi checked mà hợp đồng cha không dự kiến.

## 1. Điều kiện của kiểu trả về

Với các kiểu thông thường không có quy tắc generic phức tạp:

| Phương thức cha trả về | Phương thức con trả về | Hợp lệ khi ghi đè? |
| --- | --- | --- |
| `Number` | `Integer` | Có; `Integer` là kiểu con của `Number` |
| `Object` | `String` | Có |
| `String` | `Object` | Không; mở rộng kiểu kết quả |
| `int` | `int` | Có |
| `int` | `long` | Không |
| `long` | `int` | Không |
| `int` | `Integer` | Không |
| `Integer` | `int` | Không |
| `void` | `void` | Có |
| `void` | `Void` | Không |

`Void` là một kiểu tham chiếu; nó không đồng nghĩa với từ khóa `void`.

Bảng giả định phương thức thực sự ghi đè: tên và tham số phù hợp, là phương thức instance và đáp ứng các điều kiện truy cập liên quan. Chỉ thay kiểu trả về cũng không tạo một overload mới để né những quy tắc trên.

## 2. Vì sao phép chuyển đổi số không đủ?

Đoạn sau cố ý minh họa lỗi:

```java
class ParentCount {
    int count() {
        return 1;
    }
}

class ChildCount extends ParentCount {
    // Không hợp lệ: long không phải kiểu trả về hợp lệ cho việc ghi đè này.
    // @Override
    // long count() {
    //     return 1L;
    // }
}
```

Trong lời gọi hoặc phép gán, Java có thể mở rộng `int` thành `long`. Nhưng đó là **chuyển đổi một giá trị**, không phải quan hệ kiểu con để đổi kiểu trả về của phương thức ghi đè.

Tương tự, trả `int` thay `long` cũng bị từ chối. Không có quy tắc “số ít bit hơn thì đồng biến”.

Boxing và unboxing không giúp đổi khai báo trả về giữa `int` và `Integer`. Trình biên dịch không tự chèn chúng để biến hai kiểu trả về đó thành một cặp ghi đè hợp lệ.

### Phân biệt chữ ký trả về với biểu thức return

Phương thức vẫn có thể chuyển đổi giá trị bên trong nhưng phải giữ khai báo phù hợp:

```java
class ValidCount extends ParentCount {
    @Override
    int count() {
        byte small = 7;
        return small; // byte được mở rộng thành int; khai báo vẫn trả int.
    }
}
```

Ở đây, điều kiện ghi đè kiểm tra kiểu trả về khai báo `int`. Quy tắc của câu lệnh `return` kiểm tra việc đưa biểu thức `small` vào kiểu kết quả ấy. Hai bước liên quan nhưng không được đồng nhất.

### Mảng nguyên thủy vẫn là kiểu tham chiếu

`int[]` là kiểu tham chiếu dù phần tử của nó là nguyên thủy. Vì vậy, phương thức cha trả `Object` có thể được ghi đè bằng phương thức trả `int[]`.

Tuy nhiên, `int[]` không phải kiểu con của `long[]`. Phép mở rộng `int → long` không tạo quan hệ tương ứng giữa hai kiểu mảng.

## 3. Ngoại lệ checked: giữ, thu hẹp hoặc bỏ

Giả sử phương thức cha khai báo:

```java
Number read() throws java.io.IOException {
    return 0;
}
```

Một phương thức ghi đè có thể:

```java
// Các khai báo minh họa, không đặt đồng thời trong cùng một lớp:
Integer read() throws java.io.IOException { return 1; }
Integer read() throws java.io.FileNotFoundException { return 1; }
Integer read() { return 1; }
```

`FileNotFoundException` là kiểu con của `IOException`. Lớp con có thể công bố rủi ro checked hẹp hơn hoặc không còn công bố rủi ro checked nào.

Các khai báo sau không phù hợp với hợp đồng cha đó:

```java
// Cố ý minh họa các khai báo bị từ chối khi ghi đè:
// Integer read() throws Exception { return 1; }
// Integer read() throws java.sql.SQLException { return 1; }
```

`Exception` rộng hơn `IOException`; `SQLException` thuộc nhánh khác. Cả hai có thể buộc người gọi xử lý thêm lỗi checked ngoài những gì phương thức cha cho phép.

Quy tắc không phải “lớp con chỉ được có tối đa một ngoại lệ”. Với mỗi kiểu ngoại lệ checked được khai báo ở phương thức con, phải có một kiểu đã khai báo ở phương thức cha bao phủ nó. Con cũng có thể bỏ bớt các kiểu mà cha đã khai báo.

Nếu cha không khai báo ngoại lệ checked nào, phương thức con không được thêm ngoại lệ checked mới. Thân phương thức con phải xử lý lỗi checked phát sinh hoặc chuyển nó thành cách báo lỗi khác phù hợp hợp đồng.

## 4. Ngoại lệ unchecked không bị giới hạn giống checked

Các ngoại lệ thuộc nhánh `RuntimeException` và `Error` là unchecked. Phương thức ghi đè có thể phát sinh hoặc khai báo thêm các kiểu này mà không vi phạm giới hạn `throws` dành cho checked exception.

Ví dụ:

```java
class ParentAction {
    void execute() {
    }
}

class ChildAction extends ParentAction {
    @Override
    void execute() throws IllegalStateException {
        throw new IllegalStateException("not ready");
    }
}
```

Đây là mã minh họa có thể biên dịch, nhưng gọi `execute` sẽ ném ngoại lệ. Khả năng biên dịch không chứng minh thiết kế thay thế tốt: lớp con vẫn cần tuân thủ kỳ vọng nghiệp vụ, tránh tạo điều kiện thất bại bất ngờ.

Cũng không nên hiểu “không ghi `throws`” là “không bao giờ có ngoại lệ”. Khai báo không liệt kê mọi khả năng lỗi unchecked của chương trình.

## 5. Ví dụ hoàn chỉnh: thu hẹp cả kết quả và ngoại lệ

Lưu thành `CovariantLimitsDemo.java`. Chương trình chạy trên Java 17+.

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class CovariantLimitsDemo {
    static class Reader {
        Number read() throws IOException {
            return 0;
        }

        int count() {
            return 1;
        }
    }

    static final class FileReader extends Reader {
        private final boolean missing;

        FileReader(boolean missing) {
            this.missing = missing;
        }

        @Override
        Integer read() throws FileNotFoundException {
            if (missing) {
                throw new FileNotFoundException("data.txt");
            }
            return 21;
        }

        @Override
        int count() {
            byte small = 7;
            return small;
        }
    }

    static final class MemoryReader extends Reader {
        @Override
        Integer read() {
            return 42;
        }
    }

    public static void main(String[] args) {
        Reader base = new FileReader(false);
        try {
            Number value = base.read();
            System.out.println("base value: " + value);
        } catch (IOException e) {
            System.out.println("base failure: " + e.getMessage());
        }

        FileReader concrete = new FileReader(true);
        try {
            Integer value = concrete.read();
            System.out.println("concrete value: " + value);
        } catch (FileNotFoundException e) {
            System.out.println("concrete failure: " + e.getMessage());
        }

        MemoryReader memory = new MemoryReader();
        Integer memoryValue = memory.read();
        System.out.println("memory value: " + memoryValue);
        System.out.println("count: " + new FileReader(false).count());
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 CovariantLimitsDemo.java
java CovariantLimitsDemo
```

Stdout:

```text
base value: 21
concrete failure: data.txt
memory value: 42
count: 7
```

### Những gì thay đổi và giữ nguyên

`Reader.read` công bố kết quả `Number` và `IOException`. `FileReader.read` thu hẹp hai phía thành `Integer` và `FileNotFoundException`. Hai điều kiện này được thỏa mãn độc lập.

`MemoryReader.read` vẫn thu hẹp kiểu trả về nhưng bỏ ngoại lệ checked trong khai báo. Người gọi biết chính xác kiểu `MemoryReader` có thể gọi phương thức đó mà không cần bắt `IOException`.

`count` ở cha và con đều khai báo trả `int`. Giá trị `byte` trong thân con được mở rộng thành `int` khi trả, không làm kiểu trả về khai báo đổi thành `byte`.

Lớp `FileReader` trong chương trình là lớp minh họa lồng, không phải `java.io.FileReader`; nó không đọc tệp thật. Cờ `missing` tạo tình huống lỗi có kết quả xác định để quan sát hợp đồng ngoại lệ.

## 6. Kiểu của tham chiếu ảnh hưởng hợp đồng nhìn thấy ở nơi gọi

Trong ví dụ:

```java
Reader base = new FileReader(false);
```

Thân phương thức thực thi là bản ghi đè ở `FileReader`, nhưng biểu thức `base.read()` được kiểm tra theo khai báo nhìn thấy từ kiểu `Reader`:

- Kiểu kết quả tại nơi gọi là `Number`.
- Người gọi phải xử lý hoặc khai báo `IOException`.

Nếu chỉ bắt `FileNotFoundException` rồi không xử lý phần còn lại của `IOException`, lời gọi qua kiểu `Reader` vẫn có thể bị từ chối khi biên dịch.

Điều tương tự áp dụng nếu viết:

```java
Reader widened = new MemoryReader();
// widened.read(); // Vẫn cần xử lý/khai báo IOException theo kiểu Reader.
```

Việc đối tượng thực tế hiện tại là `MemoryReader` không tự loại bỏ yêu cầu checked ở lời gọi qua tham chiếu cha.

Ngược lại, lời gọi `memory.read()` với biến khai báo là `MemoryReader` nhìn thấy khai báo không có `throws` checked và kết quả `Integer`. Đây là khác biệt giữa hợp đồng được kiểm tra khi biên dịch và lựa chọn triển khai khi chạy.

## 7. Kiểu trả về đồng biến không “bù” cho throws sai

Đoạn sau vẫn không hợp lệ dù kiểu trả về đã thu hẹp đúng:

```java
class ParentRead {
    Number read() throws java.io.IOException {
        return 0;
    }
}

class InvalidRead extends ParentRead {
    // Không hợp lệ vì Exception mở rộng hợp đồng checked:
    // @Override
    // Integer read() throws Exception {
    //     return 1;
    // }
}
```

Cũng không thể sửa một kiểu trả về nguyên thủy sai chỉ bằng cách bỏ ngoại lệ ở con. Mỗi điều kiện phải được đáp ứng: kiểu kết quả, ngoại lệ checked, chữ ký ghi đè và mức truy cập đều cần hợp lệ.

`throws` không thuộc chữ ký dùng để phân biệt overload. Không thể tạo hai phương thức có cùng tên và cùng tham số trong một lớp chỉ bằng cách đổi danh sách ngoại lệ.

Nếu một phương thức đồng thời triển khai nhiều hợp đồng interface, nó phải đáp ứng giới hạn ngoại lệ của tất cả các phương thức mà nó triển khai. Không được tùy ý chọn hợp đồng rộng nhất rồi bỏ qua các hợp đồng còn lại.

## 8. Kiểm tra nhanh trước khi sửa lỗi

| Câu hỏi | Điều cần kiểm tra |
| --- | --- |
| Đã thật sự ghi đè chưa? | Tên, tham số, quan hệ lớp/interface và `@Override` |
| Kết quả là nguyên thủy hay tham chiếu? | Nguyên thủy giữ đúng kiểu; tham chiếu có thể thu hẹp phù hợp |
| Có đang nhầm chuyển đổi giá trị với thay đổi khai báo không? | `int → long` trong biểu thức không cho phép đổi kiểu trả về ghi đè |
| Ngoại lệ mới có phải checked không? | Xác định nhánh kế thừa của ngoại lệ |
| Mỗi ngoại lệ checked của con được cha cho phép chưa? | Cùng kiểu hoặc kiểu con của ngoại lệ đã khai báo ở cha |
| Người gọi nhìn thấy kiểu tham chiếu nào? | Kiểu đó quyết định kết quả và nghĩa vụ xử lý checked tại lời gọi |

Dùng `@Override` giúp trình biên dịch chỉ ra sớm rằng một khai báo không đáp ứng ý định ghi đè. Không bỏ annotation này chỉ để làm mất thông báo mà chưa hiểu lỗi.

## 9. Tự kiểm tra

1. Cha trả `int`, con trả `short`: có đồng biến hợp lệ không?
2. Cha trả `Number`, con trả `Integer` nhưng đổi `throws IOException` thành `throws Exception`: hợp lệ không?
3. Cha khai báo `throws IOException`, con có thể bỏ `throws` không?
4. Cha không khai báo checked exception, con thêm `IllegalArgumentException` có bị giới hạn checked cấm không?
5. Gọi `read` qua biến `Reader` trỏ đến `MemoryReader` có tự bỏ nghĩa vụ xử lý `IOException` không?

Đáp án:

1. Không; kiểu trả về nguyên thủy phải giữ nguyên.
2. Không; kết quả hợp lệ nhưng ngoại lệ checked bị mở rộng.
3. Có, miễn thân phương thức đáp ứng quy tắc xử lý ngoại lệ.
4. Không; đó là unchecked exception, nhưng thiết kế vẫn phải phù hợp hợp đồng.
5. Không; lời gọi được kiểm tra theo kiểu tham chiếu `Reader`.

## Tài liệu đối chiếu

Xem [JLS 21 §8.4.5 — Method Result](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.5), [§8.4.8.3 — Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.8.3) và [§11.1.1 — The Kinds of Exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.1.1).
