# Tự tham chiếu kiểu với Comparable&lt;T&gt; và kiểu fluent

## 1. F-bounded polymorphism

Một tham số kiểu có thể tự xuất hiện trong bound của chính nó, ví dụ **T extends Comparable&lt;T&gt;** hoặc **T extends Builder&lt;T&gt;**. Mẫu này thường gọi là F-bounded polymorphism. Nó giúp compiler giữ thông tin về kiểu cụ thể trong các API so sánh hoặc chuỗi lời gọi fluent.

Đây là ràng buộc kiểu ở thời điểm biên dịch, không phải self type riêng của Java và không tự bảo đảm rằng mọi lớp con đều thiết kế đúng.

## 2. Comparable&lt;T&gt; giữ kiểu đối tượng được so sánh

~~~java
record Version(int major, int minor) implements Comparable<Version> {
    @Override
    public int compareTo(Version other) {
        int order = Integer.compare(major, other.major);
        if (order != 0) {
            return order;
        }
        return Integer.compare(minor, other.minor);
    }
}
~~~

Khi Version triển khai Comparable&lt;Version&gt;, phương thức compareTo nhận Version. Giá trị âm nghĩa là đối tượng hiện tại đứng trước đối số, 0 nghĩa là bằng nhau theo thứ tự tự nhiên, còn giá trị dương nghĩa là đứng sau. Không cần trả đúng -1 hoặc 1.

Dùng Integer.compare/Long.compare thay vì phép trừ trực tiếp, vì phép trừ có thể tràn số. Thứ tự compareTo nên có tính đối xứng về dấu, bắc cầu và nhất quán; Java khuyến nghị thứ tự tự nhiên nhất quán với equals, đặc biệt khi dùng TreeSet hoặc TreeMap.

Một API tổng quát thường dùng bound **T extends Comparable<? super T>** để chấp nhận kiểu có thể so sánh với T hoặc một kiểu cha phù hợp của T.

## 3. Giữ kiểu lớp con trong API fluent

Nếu phương thức ở lớp cha trả về chính kiểu cha, chuỗi lời gọi có thể mất các phương thức chỉ có ở lớp con:

~~~java
class BaseBuilder {
    BaseBuilder name(String value) {
        return this;
    }
}
~~~

Nếu UserBuilder bổ sung email(String), lời gọi new UserBuilder().name("Ada").email("ada@example.com") không biên dịch được sau name(), vì biểu thức có kiểu BaseBuilder.

Mẫu tự tham chiếu giải quyết vấn đề:

~~~java
abstract class Builder<T extends Builder<T>> {
    public T name(String value) {
        return self();
    }

    protected abstract T self();
}
~~~

Lớp con điền kiểu của chính nó vào T. Phương thức self() giúp lớp cơ sở trả về giá trị có kiểu cụ thể mà không cần unchecked cast như (T) this.

## 4. Ví dụ chạy được

Lưu mã vào **FluentBuilderDemo.java**:

~~~java
public class FluentBuilderDemo {
    abstract static class SelfBuilder<T extends SelfBuilder<T>> {
        private String name;

        public T name(String name) {
            this.name = name;
            return self();
        }

        protected abstract T self();

        protected String nameValue() {
            return name;
        }
    }

    static final class UserBuilder extends SelfBuilder<UserBuilder> {
        private String email;

        public UserBuilder email(String email) {
            this.email = email;
            return self();
        }

        @Override
        protected UserBuilder self() {
            return this;
        }

        User build() {
            return new User(nameValue(), email);
        }
    }

    record User(String name, String email) {}

    public static void main(String[] args) {
        User user = new UserBuilder()
                .name("Ada")
                .email("ada@example.com")
                .build();
        System.out.println(user);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac FluentBuilderDemo.java
java FluentBuilderDemo
~~~

Kết quả:

~~~text
User[name=Ada, email=ada@example.com]
~~~

Sau name("Ada"), kiểu biểu thức vẫn là UserBuilder nên có thể gọi email() rồi build(). Không cần cast vì self() trả về UserBuilder.

## 5. Giới hạn và lỗi thường gặp

- **F-bound không phải self type tuyệt đối:** một lớp con vẫn có thể khai báo quan hệ không phù hợp nếu thiết kế cho phép; hãy giữ type argument nhất quán và giới hạn kế thừa khi cần.
- **Không dùng unchecked cast tùy tiện:** (T) this có thể che lỗi ở cây kế thừa. Mẫu self() abstract buộc lớp con cung cấp kiểu trả về rõ ràng.
- **Không nhầm compareTo với equals:** hai hợp đồng khác nhau; quyết định rõ các trường tham gia thứ tự.
- **Không so sánh số bằng phép trừ:** dùng các hàm compare chuẩn để tránh overflow.
- **Không thêm F-bound chỉ vì API có nhiều lớp:** dùng nó khi thật sự cần giữ kiểu cụ thể trong kết quả hoặc hợp đồng so sánh.

F-bounded polymorphism phù hợp với Comparable, builder và API fluent có nhiều tầng kế thừa. Với class/interface bound thông thường, xem bài về type bounds; với các bound kết hợp bằng &, xem bài về intersection type.