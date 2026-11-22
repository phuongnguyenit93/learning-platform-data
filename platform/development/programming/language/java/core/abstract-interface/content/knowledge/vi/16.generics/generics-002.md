# Triển khai interface với tham số kiểu cụ thể hoặc giữ tham số kiểu trong Java

## 1. Hai lựa chọn khi implements

Giả sử một interface khai báo hợp đồng tổng quát:

~~~java
interface Processor<T> {
    T process(T value);
}
~~~

Khi triển khai interface, class thường chọn một trong hai hướng:

- **Cố định kiểu:** dùng một type argument cụ thể, chẳng hạn implements Processor&lt;String&gt;. Lớp cam kết hỗ trợ hợp đồng cho String.
- **Giữ tính tổng quát:** khai báo tham số kiểu trên chính lớp, chẳng hạn class IdentityProcessor&lt;T&gt; implements Processor&lt;T&gt;. Lớp giữ quan hệ kiểu và có thể được sử dụng với nhiều type argument.

Chọn cách nào phụ thuộc vào trách nhiệm của implementation. Một bộ chuẩn hóa chuỗi có thể chuyên biệt cho String; một bộ chuyển tiếp giá trị có thể giữ nguyên T.

## 2. Cố định tham số kiểu

~~~java
interface Processor<T> {
    T process(T value);
}

final class TrimProcessor implements Processor<String> {
    @Override
    public String process(String value) {
        return value.trim();
    }
}
~~~

Trong mệnh đề **implements Processor&lt;String&gt;**, T được thay bằng String. Vì vậy, chữ ký phải nhận String và trả String. **TrimProcessor** không cần khai báo tham số kiểu riêng, vì kiểu hỗ trợ đã được xác định.

~~~java
Processor<String> processor = new TrimProcessor();
String result = processor.process("  Java  ");
~~~

Trình biên dịch chấp nhận lời gọi với String và từ chối giá trị không tương thích như Integer. Cách này phù hợp với adapter chuyên biệt, bộ chuẩn hóa chuỗi, hoặc repository chỉ quản lý một kiểu thực thể.

## 3. Giữ tham số kiểu của interface

~~~java
interface Processor<T> {
    T process(T value);
}

final class IdentityProcessor<T> implements Processor<T> {
    @Override
    public T process(T value) {
        return value;
    }
}
~~~

**IdentityProcessor&lt;T&gt;** khai báo T ở cấp class rồi chuyển chính tham số đó vào **Processor&lt;T&gt;**. T không bị cố định tại khai báo lớp:

~~~java
Processor<String> textProcessor = new IdentityProcessor<>();
Processor<Integer> numberProcessor = new IdentityProcessor<>();

String text = textProcessor.process("hello");
Integer number = numberProcessor.process(42);
~~~

Toán tử kim cương <> cho phép compiler suy luận type argument trong ngữ cảnh phù hợp. Với tham chiếu Processor&lt;String&gt;, chữ ký nhìn thấy ở nơi gọi nhận String và trả String; với Processor&lt;Integer&gt;, nó nhận Integer và trả Integer. Một implementation tổng quát vẫn chỉ đúng trong những giới hạn mà T cho phép. Nếu thuật toán cần khả năng đặc biệt như so sánh hoặc gọi doubleValue(), hãy khai báo type bound tương ứng thay vì giả định mọi T đều có hành vi đó.

## 4. Ánh xạ nhiều tham số kiểu

Khi interface có nhiều tham số, implementation phải cung cấp một type argument tương ứng cho từng vị trí:

~~~java
interface Converter<S, T> {
    T convert(S source);
}

final class StringLengthConverter implements Converter<String, Integer> {
    @Override
    public Integer convert(String source) {
        return source.length();
    }
}

final class IdentityConverter<U> implements Converter<U, U> {
    @Override
    public U convert(U source) {
        return source;
    }
}
~~~

**StringLengthConverter** cố định kiểu nguồn là String và kiểu đích là Integer. **IdentityConverter&lt;U&gt;** giữ một tham số U cho cả nguồn lẫn đích. Tên tham số của lớp triển khai không cần giống tên trong interface; điều quan trọng là vị trí và quan hệ kiểu phải đúng.

Type argument có thể là kiểu đã tham số hóa, ví dụ **Holder<List&lt;String&gt;>**, miễn là kiểu đó hợp lệ. Java không cho dùng primitive làm type argument; hãy dùng wrapper như Integer và dựa vào boxing/unboxing khi phù hợp.

## 5. Giữ kiểu qua kế thừa

Một lớp abstract có thể giữ tham số kiểu rồi để lớp con cố định nó:

~~~java
interface Repository<T> {
    T findById(long id);
}

abstract class BaseRepository<T> implements Repository<T> {
    // Lớp abstract được phép trì hoãn findById.
}

final class User {
    private final long id;

    User(long id) {
        this.id = id;
    }

    long id() {
        return id;
    }
}

final class UserRepository extends BaseRepository<User> {
    @Override
    public User findById(long id) {
        return new User(id);
    }
}
~~~

**BaseRepository&lt;T&gt;** chuyển tiếp T sang interface và có thể trì hoãn việc triển khai vì nó là abstract. **UserRepository** cố định T thành User, nên phương thức được triển khai phải trả User. Nếu lớp con chưa triển khai phương thức abstract và cũng không kế thừa implementation phù hợp, lớp đó phải tiếp tục là abstract.

## 6. Các lỗi biên dịch điển hình

### Dùng T nhưng không khai báo T

~~~java
interface Processor<T> {
    T process(T value);
}

// Không hợp lệ: T không thuộc phạm vi BrokenProcessor.
class BrokenProcessor implements Processor<T> {
}
~~~

Nếu muốn lớp tổng quát, khai báo **BrokenProcessor&lt;T&gt; implements Processor&lt;T&gt;**. Nếu lớp chỉ xử lý chuỗi, dùng **Processor&lt;String&gt;** và khai báo chữ ký nhận/trả String.

### Giữ T nhưng triển khai chữ ký chuyên biệt

~~~java
interface Processor<T> {
    T process(T value);
}

// Không hợp lệ: lớp tuyên bố hỗ trợ mọi T nhưng chỉ nhận String.
class BadProcessor<T> implements Processor<T> {
    @Override
    public String process(String value) {
        return value.trim();
    }
}
~~~

**BadProcessor&lt;T&gt;** hứa đáp ứng Processor cho bất kỳ T nào, nhưng process(String) không thể xử lý Integer hoặc kiểu T khác. Hãy cố định T thành String nếu implementation chỉ hỗ trợ chuỗi, hoặc triển khai process(T) nếu class thực sự tổng quát.

### Cố định T nhưng dùng chữ ký sai

~~~java
interface Processor<T> {
    T process(T value);
}

class WrongProcessor implements Processor<String> {
    // Không override được process(String).
    public Object process(Object value) {
        return value;
    }
}
~~~

Sau khi thay T bằng String, hợp đồng yêu cầu process(String) trả String. process(Object) là một phương thức khác; annotation @Override sẽ giúp compiler phát hiện lỗi khi đặt trên chữ ký không phù hợp.

## 7. Chọn thiết kế theo trách nhiệm

| Nhu cầu | Khai báo gợi ý | Lý do |
| --- | --- | --- |
| Chỉ xử lý chuỗi | implements Processor&lt;String&gt; | Hợp đồng cụ thể, dễ dùng |
| Cùng thuật toán cho nhiều kiểu | class ProcessorImpl&lt;T&gt; implements Processor&lt;T&gt; | Giữ kiểu qua đầu vào và kết quả |
| Chuyển đổi hai kiểu khác nhau | implements Converter&lt;String, Integer&gt; | Nguồn và đích rõ ràng |
| Lớp cơ sở trì hoãn implementation | abstract class BaseRepository&lt;T&gt; implements Repository&lt;T&gt; | Lớp con quyết định kiểu sau |
| Cần khả năng riêng của một nhóm kiểu | Dùng type bound phù hợp | Compiler kiểm tra điều kiện trước khi gọi |

Không thêm tham số kiểu chỉ để làm class trông tổng quát hơn. Ngược lại, đừng cố định kiểu quá sớm nếu implementation thực sự hỗ trợ nhiều kiểu.

**Phạm vi của bài này:** tính bất biến và wildcard ảnh hưởng đến các kiểu generic ở ranh giới API; type erasure và bridge method giải thích chữ ký ở runtime. Hai chủ đề đó có bài riêng trong chương. Khi implements, điều cần kiểm tra trước tiên là mỗi type parameter đã được cố định hoặc chuyển tiếp nhất quán qua mọi chữ ký chưa.