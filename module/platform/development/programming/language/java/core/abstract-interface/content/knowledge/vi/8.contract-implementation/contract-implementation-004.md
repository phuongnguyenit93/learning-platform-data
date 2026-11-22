# Dùng phương thức kế thừa từ lớp cha để đáp ứng interface

## 1. Ý tưởng cốt lõi

Khi một lớp khai báo `implements InterfaceName`, Java yêu cầu lớp cụ thể đó có cách triển khai hợp lệ cho mọi phương thức trừu tượng của interface. **Không bắt buộc phải viết lại phương thức ngay trong lớp khai báo `implements`**: một phương thức cụ thể, `public`, có chữ ký phù hợp được **kế thừa từ lớp cha** cũng có thể đáp ứng hợp đồng.

Ví dụ, lớp cha `BaseRecord` đã cung cấp `public String code()`. Lớp con `Record` kế thừa phương thức này và khai báo `implements HasCode`, vì vậy Java chấp nhận `Record` dù thân lớp không có phương thức `code()` riêng.

Cần phân biệt hai việc:

- **Có sẵn phương thức:** `BaseRecord` định nghĩa `code()` và `Record` được kế thừa cách thực hiện.
- **Mang kiểu interface:** chỉ lớp được khai báo là triển khai `HasCode` (hoặc kế thừa từ một lớp đã triển khai interface đó) mới có thể sử dụng như một giá trị `HasCode`. Việc lớp cha tình cờ có phương thức cùng chữ ký không tự động biến lớp cha thành một implementation của interface. Java dùng khai báo `implements`, không dùng cơ chế tự động coi mọi kiểu có đủ phương thức là một interface.

## 2. Ví dụ Java 17+ chạy được

Lưu vào tệp `InheritedInterfaceDemo.java`:

```java
public class InheritedInterfaceDemo {
    interface HasCode {
        String code(); // Mặc định là public abstract
    }

    static class BaseRecord {
        public String code() {
            return "BASE-001";
        }
    }

    static class Record extends BaseRecord implements HasCode {
        // Kế thừa BaseRecord.code(), không cần override.
    }

    static class SpecialRecord extends Record {
        @Override
        public String code() {
            return "SPECIAL-002";
        }
    }

    public static void main(String[] args) {
        HasCode first = new Record();
        HasCode second = new SpecialRecord();

        System.out.println(first.code());
        System.out.println(second.code());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 InheritedInterfaceDemo.java
java InheritedInterfaceDemo
```

Kết quả chính xác:

```text
BASE-001
SPECIAL-002
```

Diễn giải từng bước:

1. `HasCode.code()` là phương thức `public abstract` dù trong interface không ghi hai từ khóa đó.
2. `BaseRecord.code()` là phương thức instance `public`, trả về `String`, khớp với phương thức interface yêu cầu.
3. `Record extends BaseRecord implements HasCode`: compiler tìm được `code()` đã kế thừa, vì vậy `Record` là lớp cụ thể hợp lệ mà không phải định nghĩa thêm `code()`.
4. `SpecialRecord` override `code()`, nên lời gọi thông qua biến kiểu `HasCode` vẫn chọn cách triển khai theo **kiểu đối tượng thực tế**: `Record` in `BASE-001`, `SpecialRecord` in `SPECIAL-002`. Đây là đa hình với dynamic dispatch.

Lưu ý: `BaseRecord` **không** được khai báo là `HasCode`; câu `HasCode x = new BaseRecord();` không biên dịch được, trong khi `HasCode x = new Record();` hợp lệ.

## 3. Điều kiện để phương thức kế thừa đáp ứng hợp đồng

Một phương thức kế thừa chỉ thay thế được việc cài đặt phương thức trừu tượng của interface nếu thỏa các quy tắc override/implement của Java:

- **Đúng tên và danh sách tham số:** chỉ trùng tên nhưng khác kiểu hoặc số lượng tham số là overload, không triển khai yêu cầu. Với generic cần xét cả quy tắc chữ ký và *type erasure*.
- **Đúng loại phương thức:** interface yêu cầu một phương thức instance thì phương thức đáp ứng phải là instance; phương thức `static` cùng tên không thể làm implementation.
- **Đủ mức truy cập:** phương thức triển khai phải là `public`, vì phương thức abstract của interface là `public`. Phương thức `protected` hoặc package-private kế thừa từ lớp cha chưa đạt yêu cầu.
- **Kiểu trả về tương thích:** kiểu trả về phải giống hoặc là kiểu con hợp lệ (*covariant return*) theo quy tắc Java. Một phương thức chỉ trùng tên và tham số nhưng có kiểu trả về không tương thích sẽ không được chấp nhận.
- **Checked exceptions hợp lệ:** phương thức triển khai không được khai báo checked exception rộng hơn mức hợp đồng interface cho phép. Unchecked exception không có ràng buộc cùng loại này.
- **Phương thức đã có thân:** đối với lớp con cụ thể, phương thức `abstract` kế thừa chưa cung cấp implementation; lớp cụ thể vẫn phải cung cấp một implementation hợp lệ.

Một phương thức `public final` có sẵn ở lớp cha **vẫn có thể** đáp ứng interface nếu chữ ký tương thích. `final` chỉ ngăn lớp con override phương thức đó, không ngăn việc dùng implementation kế thừa để thỏa hợp đồng.

## 4. Lỗi phổ biến: phương thức lớp cha không phải public

Đoạn sau **cố ý không biên dịch**:

```java
interface Executable {
    void execute();
}

class Base {
    protected void execute() {
        System.out.println("Run");
    }
}

class Job extends Base implements Executable {
    // Lỗi: execute() kế thừa chỉ là protected,
    // trong khi Executable.execute() yêu cầu public.
}
```

`protected` cho phép lớp con truy cập phương thức, nhưng **không** đủ để triển khai hợp đồng `public` của interface. Có thể sửa bằng cách override với mức truy cập `public`:

```java
class Job extends Base implements Executable {
    @Override
    public void execute() {
        super.execute();
    }
}
```

Trong phiên bản sửa, `Job.execute()` là điểm truy cập `public` đáp ứng `Executable`; `super.execute()` vẫn tái sử dụng logic của lớp cha. Hai khối mã trong mục này minh họa lỗi và cách sửa, không phải các chương trình độc lập có `main`.

Một số bẫy tương tự:

- Lớp cha có `static void execute()` còn interface yêu cầu `void execute()`: phương thức static không thể thực hiện hợp đồng instance.
- Lớp cha có `public void execute(int n)` nhưng interface yêu cầu `void execute()`: khác tham số nên không đáp ứng.
- Lớp cha chỉ khai báo `public abstract void execute()`: lớp con cụ thể vẫn cần triển khai.
- Lớp cha có phương thức `private` cùng tên: phương thức private không được lớp con kế thừa như một phương thức có thể override để đáp ứng interface.

## 5. Nếu interface có phương thức default thì sao?

Quy tắc **class wins**: khi lớp cha cung cấp phương thức instance kế thừa thích hợp, nó được ưu tiên hơn phương thức `default` cùng chữ ký từ interface. Đây là hành vi có chủ đích, giúp thêm phương thức default vào interface mà không bất ngờ thay thế logic sẵn có của lớp cha.

Lưu đoạn sau vào tệp `ClassWinsDemo.java`:

```java
public class ClassWinsDemo {
    interface Greeter {
        default String greet() {
            return "from interface";
        }
    }

    static class Parent {
        public String greet() {
            return "from parent";
        }
    }

    static class Child extends Parent implements Greeter {
    }

    public static void main(String[] args) {
        Child child = new Child();
        Greeter asInterface = child;

        System.out.println(child.greet());
        System.out.println(asInterface.greet());
    }
}
```

Chạy `javac -encoding UTF-8 ClassWinsDemo.java`, rồi `java ClassWinsDemo`. Kết quả:

```text
from parent
from parent
```

Dù tham chiếu thứ hai có kiểu `Greeter`, phương thức được gọi vẫn là implementation kế thừa từ `Parent`. Nếu lớp con override `greet()` hợp lệ, implementation override mới được gọi.

## 6. Khi nào nên tận dụng phương thức kế thừa?

Cách này phù hợp khi lớp cha đã có implementation đúng ngữ nghĩa của interface và bạn muốn lớp con công bố rõ hợp đồng mà không nhân bản code. Chẳng hạn, một lớp cha đã có thao tác `id()` đáng tin cậy, còn lớp con cần được truyền vào API nhận interface `Identifiable`.

Khi đánh giá thiết kế, hãy tự hỏi:

1. Phương thức kế thừa có đúng **ý nghĩa** mà interface hứa hẹn không, hay chỉ tình cờ trùng chữ ký?
2. Phương thức có đáp ứng đủ `public`, chữ ký, kiểu trả về và checked exceptions không?
3. Có phải thay đổi trong lớp cha sẽ làm thay đổi hành vi của những lớp con triển khai interface không?
4. Nếu lớp con cần hành vi riêng, có nên override rõ ràng thay vì kế thừa nguyên bản không?

**Ghi nhớ:** `implements` xác lập cam kết về kiểu và hợp đồng; phương thức `public` phù hợp được kế thừa từ lớp cha có thể thực hiện cam kết đó. Java kiểm tra tính hợp lệ lúc biên dịch và chọn implementation phù hợp với đối tượng thực tế lúc chạy.
