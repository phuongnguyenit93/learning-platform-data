# Khai báo generic interface và generic abstract class trong Java

## 1. Generics giải quyết vấn đề gì?

Generics cho phép một interface hoặc class biểu diễn mối quan hệ kiểu mà không phải viết nhiều phiên bản chỉ khác kiểu dữ liệu. Tham số kiểu như **T**, **S**, **K** và **V** được khai báo tại một kiểu; khi sử dụng, người gọi cung cấp đối số kiểu như **String**, **Integer** hoặc **User**.

~~~java
interface Converter<S, T> {
    T convert(S source);
}

abstract class Repository<T, ID> {
    public abstract T findById(ID id);
}
~~~

Trong **Converter&lt;S, T&gt;**, S là kiểu đầu vào và T là kiểu kết quả. Trong **Repository&lt;T, ID&gt;**, T là kiểu đối tượng được quản lý còn ID là kiểu khóa. Các kiểu này được giữ xuyên suốt chữ ký, nên trình biên dịch có thể phát hiện lời gọi không phù hợp trước khi chạy.

## 2. Khai báo generic interface

Một tham số kiểu:

~~~java
interface Box<T> {
    T get();
}
~~~

Nhiều tham số kiểu:

~~~java
interface Pair<K, V> {
    K key();
    V value();
}
~~~

Tên T, K và V chỉ là quy ước, không phải từ khóa. Có thể dùng tên mô tả như Source, Result hoặc ID nếu điều đó giúp hợp đồng dễ đọc hơn.

Khi một lớp triển khai `Box<String>`, hợp đồng `get()` có kiểu trả về `String`; nếu lớp giữ `T` và triển khai `Box<T>`, hợp đồng vẫn tổng quát. Cách lựa chọn và triển khai đầy đủ được phân tích ở bài tiếp theo.

Một interface cũng có thể kế thừa interface generic và truyền tiếp hoặc cố định tham số:

~~~java
interface Source<T> {
    T read();
}

interface NamedSource extends Source<String> {
    String name();
}

interface TransformSource<S, T> extends Source<T> {
    S original();
}
~~~

**NamedSource** kế thừa hợp đồng đã chọn T = String, nên read() trả về String. **TransformSource&lt;S, T&gt;** giữ cả hai tham số và chuyển T sang Source&lt;T&gt;. Interface có thể kế thừa nhiều interface; các chữ ký kế thừa vẫn phải tương thích với quy tắc Java thông thường.

## 3. Khai báo generic abstract class

Generic abstract class có thể dùng tham số kiểu trong field, constructor, phương thức thường và phương thức abstract:

~~~java
abstract class Holder<T> {
    private final T value;

    protected Holder(T value) {
        this.value = value;
    }

    public T getValue() {
        return value;
    }

    public abstract String describe();
}
~~~

Với **Holder&lt;String&gt;**, getValue() có kiểu trả về String. Constructor nhận T để khởi tạo trạng thái, còn describe() để lớp cụ thể cung cấp hành vi riêng. Không thể khởi tạo trực tiếp một abstract class bằng new.

Một class có thể khai báo nhiều tham số kiểu:

~~~java
abstract class Repository<T, ID> {
    public abstract T findById(ID id);
    public abstract void save(T entity);
}
~~~

**Repository&lt;User, Long&gt;** vì vậy nhận khóa Long và trả về User. Trong ví dụ `Holder<T>` phía trên, constructor `Holder(T value)` sử dụng T đã khai báo ở cấp class, chứ không khai báo type parameter mới. Java cũng cho phép generic constructor có type parameter riêng, độc lập với T của class.

## 4. Nối interface với abstract class

Abstract class có thể thực hiện interface và chia sẻ phần cài đặt chung cho các lớp con:

~~~java
interface Identifiable<ID> {
    ID id();
}

abstract class Entity<ID> implements Identifiable<ID> {
    private final ID id;

    protected Entity(ID id) {
        this.id = id;
    }

    @Override
    public final ID id() {
        return id;
    }
}

final class User extends Entity<Long> {
    private final String name;

    User(Long id, String name) {
        super(id);
        this.name = name;
    }

    String name() {
        return name;
    }
}
~~~

**Entity&lt;ID&gt;** chuyển tiếp ID sang interface và cung cấp cách lưu ID dùng chung. **User** cố định ID thành Long. Một abstract class có thể triển khai một phần hợp đồng và để phần còn lại cho lớp con; lớp cụ thể phải hoàn thành các phương thức abstract chưa được cài đặt. Java cho phép một class extends một class cha và implements nhiều interface.

## 5. Ví dụ chạy được

Lưu chương trình sau vào **GenericDeclarationDemo.java**:

~~~java
interface Mapper<S, T> {
    T map(S source);
}

interface Identifiable<ID> {
    ID id();
}

abstract class Entity<ID> implements Identifiable<ID> {
    private final ID id;

    protected Entity(ID id) {
        this.id = id;
    }

    @Override
    public final ID id() {
        return id;
    }
}

final class User extends Entity<Long> {
    private final String name;

    User(Long id, String name) {
        super(id);
        this.name = name;
    }

    String name() {
        return name;
    }
}

abstract class Repository<T, ID> {
    public abstract T findById(ID id);
}

final class UserRepository extends Repository<User, Long> {
    @Override
    public User findById(Long id) {
        return new User(id, "Lan");
    }
}

public class GenericDeclarationDemo {
    public static void main(String[] args) {
        Mapper<String, Integer> length = String::length;
        System.out.println("length=" + length.map("Java"));

        Repository<User, Long> repository = new UserRepository();
        User user = repository.findById(7L);
        System.out.println("user=" + user.name() + ", id=" + user.id());
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac GenericDeclarationDemo.java
java GenericDeclarationDemo
~~~

Kết quả:

~~~text
length=4
user=Lan, id=7
~~~

Trong ví dụ này, Mapper liên kết String đầu vào với Integer đầu ra; Entity giữ ID có kiểu; Repository liên kết kiểu thực thể với kiểu khóa. Các quan hệ đó thể hiện ngay trong khai báo và không cần cast ở nơi gọi.

## 6. Những lỗi khai báo cần tránh

- **Dùng primitive làm type argument:** List<int> không hợp lệ; dùng List&lt;Integer&gt;.
- **Dùng type parameter ngoài phạm vi:** T chỉ hợp lệ nếu được khai báo trên class, interface hoặc phương thức hiện tại.
- **Dùng T của instance class trong static member:** static member không gắn với một đối tượng có T cụ thể. Một static generic method phải khai báo tham số kiểu riêng nếu cần dùng kiểu tổng quát.
- **Nhầm extends với implements:** class dùng extends để kế thừa một class và implements để thực hiện interface. Trong giới hạn type parameter, extends được dùng cho cả class lẫn interface.
- **Dùng raw type không cần thiết:** khai báo Box thay vì Box&lt;String&gt; làm mất một phần kiểm tra kiểu.

Các bài tiếp theo đi sâu vào việc cố định hay giữ tham số kiểu khi implements, phạm vi của generic method, type bounds, wildcard và type erasure. Ở bài khai báo này, hãy tập trung xác định tham số kiểu nào thuộc về kiểu nào và cách nó được truyền qua chữ ký.