# Che khuất trường và phương thức `static` theo kiểu khai báo trong Java

Khi một class con khai báo **field cùng tên** với field được thừa hưởng từ class cha, Java gọi đó là **field hiding** — *che khuất trường*. Khi class con khai báo **static method** có chữ ký tương ứng static method của class cha, đó là **static method hiding** — *che khuất phương thức static*. Hai cơ chế đều dễ bị nhầm với **method overriding**, nhưng nguyên tắc chọn member khác nhau căn bản.

~~~java
class Parent {
    static String category = "PARENT";

    static String kind() {
        return "Parent.kind";
    }

    String describe() {
        return "Parent.describe";
    }
}

class Child extends Parent {
    static String category = "CHILD"; // Field hiding.

    static String kind() {           // Static method hiding.
        return "Child.kind";
    }

    @Override
    String describe() {              // Instance method overriding.
        return "Child.describe";
    }
}
~~~

Nếu tham chiếu được khai báo là `Parent reference = new Child();`, các biểu thức:

~~~java
reference.category
reference.kind()
reference.describe()
~~~

**không phải lúc nào cũng chọn Child**. Field và static method được chọn theo **kiểu compile-time của biểu thức `reference`** (Parent), còn instance method được override dispatch theo **actual runtime object** (Child). Đây là khác biệt cốt lõi của bài.

Bài thuộc Java Core — **Class & Object / Kế thừa và đa hình**, dùng **Java 17+**. Mỗi chương trình chạy độc lập có tên file, lệnh `javac`/`java` và stdout cụ thể. Đoạn không độc lập hoặc cố ý không biên dịch sẽ được ghi chú.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **field hiding**, **static method hiding** và **instance method overriding**.
2. Hiểu khái niệm **kiểu khai báo/compile-time type** của reference và **runtime class** của object.
3. Dự đoán field và static method được chọn khi một biến `Parent` trỏ tới object `Child`.
4. Hiểu vì sao `@Override` không được dùng cho static method hiding.
5. Giải thích tác dụng của ép kiểu `(Parent)`, `(Child)` đối với **member selection**.
6. Phân biệt việc **chọn field theo tên và compile-time type** với việc object thật đang lưu instance fields.
7. Biết rằng class con khai báo field trùng tên có thể tạo **hai fields khác nhau**, chứ không phải đổi một field duy nhất.
8. Biết khi nào static field/method được kế thừa và khi nào bị che khuất.
9. Phân biệt `Parent.staticMember` với `reference.staticMember`; nhận biết cú pháp qua object gây hiểu lầm.
10. Dự đoán trường hợp **reference null** vẫn được dùng làm qualifier truy cập static member.
11. Hiểu **qualifier expression vẫn có thể được đánh giá**, kể cả khi giá trị reference không cần cho static access.
12. Phân biệt **overloading** được chọn tại compile time với **overriding** dispatch tại runtime.
13. Biết điều kiện tương thích access, return type, `throws`, `final` và static/instance khi hiding.
14. Biết static members trong **interfaces** khác static methods của class về inheritance.
15. Hiểu class initialization khi đọc static field được thừa hưởng qua tên subclass.
16. Tránh dùng field hiding như cơ chế “đa hình dữ liệu”.
17. Thiết kế giải pháp thay thế bằng instance method, constructor injection hoặc method có tên rõ.
18. Viết tests phân biệt compile-time member selection và runtime virtual dispatch.

## 2. Hai loại “kiểu” phải phân biệt

Ví dụ:

~~~java
Parent ref = new Child();
~~~

Có hai thông tin cùng tồn tại:

- **Declared/compile-time type** của biểu thức `ref` là **Parent**.
- **Runtime class** của object mà `ref` trỏ tới là **Child**.

Sơ đồ:

~~~text
  local variable
  ref : Parent
      |
      v
  +--------------------+
  | Child object       |
  | extends Parent     |
  +--------------------+

  ref.field       -> Tra field bằng compile-time type Parent.
  ref.staticCall() -> Chọn static method bằng compile-time type Parent.
  ref.virtualCall()-> Runtime dispatch đến override ở Child nếu hợp lệ.
~~~

Việc `new Child()` **không làm compiler đổi khai báo của `ref` thành Child**. Compiler chỉ biết `ref` có kiểu Parent; vì Child là subtype của Parent nên assignment hợp lệ.

### Quy tắc nhớ ngắn

> **Fields và static methods không đa hình theo runtime receiver. Những instance methods được override hợp lệ mới có dynamic dispatch.**

Đây là quy tắc thực hành nền tảng, dù chi tiết Java về overload, method signatures, access, hiding và inheritance còn phải xét ngữ cảnh.

## 3. Thuật ngữ chính xác

| Khái niệm | Member | Điều xảy ra |
| --- | --- | --- |
| **Field hiding** | Field trùng tên ở subclass | Khai báo mới che field được kế thừa khi tra cứu bằng tên trong ngữ cảnh thích hợp |
| **Static method hiding** | Static method cùng chữ ký phù hợp ở subclass | Subclass method che superclass static method; lựa chọn không dựa vào actual receiver object |
| **Instance method overriding** | Instance method ở subclass ghi đè method được kế thừa | Dispatch tới implementation thích hợp theo runtime object |
| **Method overloading** | Các methods cùng tên nhưng khác parameter lists | Chọn overload phù hợp chủ yếu theo compile-time argument types |
| **Shadowing** | Một khai báo local/parameter che tên khai báo khác trong scope | Tra tên có thể ưu tiên biến local hơn field |
| **Upcasting** | Gán Child reference vào biến Parent | Actual object không bị cắt/biến thành Parent object |
| **Downcasting** | Ép Parent reference thành Child khi runtime object thực sự phù hợp | Cho phép truy cập members theo type Child, có thể ném ClassCastException |

Chữ **hiding** không có nghĩa Java xóa field/method của Parent khỏi runtime. Nó nói về **khai báo nào được chọn khi giải tên** trong một ngữ cảnh compile-time.

## 4. Field hiding với hai static fields cùng tên

Ví dụ:

~~~java
class Parent {
    static int value = 10;
}

class Child extends Parent {
    static int value = 20;
}
~~~

Có **hai biến static riêng**:

- `Parent.value` được khai báo bởi Parent.
- `Child.value` được khai báo bởi Child.

Chúng có thể mang giá trị khác nhau. Thay `Child.value` không tự thay `Parent.value`.

### Truy cập qua tên class

~~~java
System.out.println(Parent.value); // 10.
System.out.println(Child.value);  // 20.
~~~

Đây là cách rõ ràng nhất.

### Truy cập qua object reference

~~~java
Parent p = new Child();
Child c = new Child();

System.out.println(p.value); // Parent.value, không phải Child.value.
System.out.println(c.value); // Child.value.
~~~

Java cho phép cú pháp `p.value` với static field (khi field accessible), nhưng **không khuyến nghị** vì dễ khiến người đọc tưởng static field thuộc riêng object p. Dùng `Parent.value` hoặc `Child.value`.

## 5. Chương trình chạy: static field hiding

Lưu file **`StaticFieldHidingDemo.java`**:

~~~java
public class StaticFieldHidingDemo {
    static class Parent {
        static int score = 10;
    }

    static final class Child extends Parent {
        static int score = 20;
    }

    public static void main(String[] args) {
        Parent parentView = new Child();
        Child childView = new Child();

        System.out.println("Parent=" + Parent.score);
        System.out.println("Child=" + Child.score);
        System.out.println("parentView=" + parentView.score);
        System.out.println("childView=" + childView.score);

        Child.score = 99;

        System.out.println("after Parent=" + Parent.score);
        System.out.println("after Child=" + Child.score);
        System.out.println("after parentView=" + parentView.score);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticFieldHidingDemo.java
java StaticFieldHidingDemo
~~~

Stdout:

~~~text
Parent=10
Child=20
parentView=10
childView=20
after Parent=10
after Child=99
after parentView=10
~~~

### Diễn giải

1. `Parent.parentView` không phải một object mới ngoài những gì `new Child()` tạo ra; biến `parentView` được khai báo kiểu Parent nhưng giữ reference tới Child object.
2. `parentView.score` được phân giải thành `Parent.score`.
3. `childView.score` được phân giải thành `Child.score`.
4. `Child.score = 99` chỉ thay field của Child.
5. `Parent.score` vẫn bằng 10; `parentView.score` tiếp tục đọc Parent.score.

Mặc dù cả hai references trỏ tới **các object có runtime class Child**, việc tra static fields không dispatch theo runtime object.

## 6. Nếu Child không khai báo field trùng tên thì sao?

~~~java
class Parent {
    static int count = 5;
}

class Child extends Parent {
    // Không khai báo count.
}
~~~

Trong ngữ cảnh được phép, `Child.count` đề cập **cùng field được khai báo trong Parent**, không tạo field mới ở Child.

~~~java
Parent.count = 7;
System.out.println(Child.count); // 7.
Child.count++;
System.out.println(Parent.count); // 8.
~~~

Phải phân biệt hai tình huống:

| Child khai báo `static int count` riêng? | `Child.count` thực sự là gì? |
| --- | --- |
| Không | Tham chiếu field được kế thừa từ Parent |
| Có | Tham chiếu field riêng của Child, che field Parent |

**Không nên nói:** “Mỗi subclass luôn có một bản copy của các static fields của superclass”. Những fields không bị khai báo lại thuộc superclass khai báo ban đầu.

## 7. Ví dụ chạy: inherited static field chỉ là một field

Lưu **`InheritedStaticFieldDemo.java`**:

~~~java
public class InheritedStaticFieldDemo {
    static class Parent {
        static int counter = 1;
    }

    static final class Child extends Parent {
    }

    public static void main(String[] args) {
        System.out.println("start=" + Parent.counter);
        Child.counter += 4;
        System.out.println("Parent=" + Parent.counter);
        System.out.println("Child=" + Child.counter);
    }
}
~~~

~~~bash
javac -encoding UTF-8 InheritedStaticFieldDemo.java
java InheritedStaticFieldDemo
~~~

Stdout:

~~~text
start=1
Parent=5
Child=5
~~~

Trong chương trình này Child không khai báo counter riêng. `Parent.counter` và `Child.counter` là cùng static field ở Parent.

Về phong cách, hãy dùng tên **class khai báo field**: `Parent.counter`. Cú pháp `Child.counter` có thể khiến người đọc nhầm counter thuộc Child.

## 8. `static method hiding` khác `override`

Với:

~~~java
class Parent {
    static String identify() {
        return "Parent";
    }
}

class Child extends Parent {
    static String identify() {
        return "Child";
    }
}
~~~

`Child.identify()` **hide** `Parent.identify()`. Một lời gọi static không dùng dynamic dispatch theo receiver object.

~~~java
Parent p = new Child();
Child c = new Child();

System.out.println(p.identify());      // Parent.
System.out.println(c.identify());      // Child.
System.out.println(Parent.identify()); // Parent.
System.out.println(Child.identify());  // Child.
~~~

Giống static fields, cú pháp `p.identify()` hợp lệ về ngữ nghĩa trong những tình huống này nhưng dễ nhầm. Nên gọi `Parent.identify()` và `Child.identify()`.

**Không dùng `@Override` cho static method hiding**: static method không override một static method của superclass. Annotation ấy trên method static sẽ khiến compiler báo lỗi vì không có một method instance thích hợp để override.

## 9. Ví dụ chạy: static hiding đối chiếu với instance overriding

Lưu **`StaticVsInstanceDispatchDemo.java`**:

~~~java
public class StaticVsInstanceDispatchDemo {
    static class Parent {
        static String category() {
            return "Parent.static";
        }

        String describe() {
            return "Parent.instance";
        }
    }

    static final class Child extends Parent {
        static String category() {
            return "Child.static";
        }

        @Override
        String describe() {
            return "Child.instance";
        }
    }

    public static void main(String[] args) {
        Parent parentView = new Child();
        Child childView = (Child) parentView;

        System.out.println("p.static=" + parentView.category());
        System.out.println("c.static=" + childView.category());
        System.out.println("p.instance=" + parentView.describe());
        System.out.println("c.instance=" + childView.describe());
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticVsInstanceDispatchDemo.java
java StaticVsInstanceDispatchDemo
~~~

Stdout:

~~~text
p.static=Parent.static
c.static=Child.static
p.instance=Child.instance
c.instance=Child.instance
~~~

### Từng lời gọi chọn gì?

- `parentView.category()`: compiler thấy Parent reference → chọn `Parent.category()`.
- `childView.category()`: compiler thấy Child reference → chọn `Child.category()`.
- `parentView.describe()`: method instance được override → runtime object Child → chạy `Child.describe()`.
- `childView.describe()`: vẫn chạy Child.describe().

Đây là một chương trình cần nắm vững: **hai references cùng một object**, nhưng static calls cho hai kết quả khác nhau do compile-time type; instance calls cho cùng kết quả do runtime dispatch.

## 10. Bảng so sánh quan trọng nhất

Giả sử:

~~~java
Parent ref = new Child();
~~~

và Child có khai báo thành viên cùng tên tương ứng với Parent.

| Biểu thức | Cơ chế chọn | Kết quả điển hình |
| --- | --- | --- |
| `ref.staticField` | Field lookup theo compile-time Parent | Parent.staticField |
| `ref.instanceField` | Field lookup theo compile-time Parent | Parent.instanceField trên object Child |
| `ref.staticMethod()` | Static method resolution theo compile-time Parent | Parent.staticMethod |
| `ref.instanceMethod()` | Dispatch theo runtime Child nếu override hợp lệ | Child.instanceMethod |
| `Parent.staticMethod()` | Qualified name Parent | Parent.staticMethod |
| `Child.staticMethod()` | Qualified name Child | Child.staticMethod |
| `((Child) ref).staticField` | Compile-time qualifier sau cast là Child | Child.staticField |
| `((Parent) ref).instanceMethod()` | Parent compile-time, nhưng virtual call | Child override vẫn chạy |

**Nhớ:** Ép kiểu chỉ thay cách compiler hiểu biểu thức, không tự thay actual object. Không có “object slicing” khi upcast một Java reference như một số cơ chế ở ngôn ngữ khác.

## 11. Field hiding cũng áp dụng cho instance fields

Một người học có thể tưởng chỉ `static` field mới bị hiding. Thực tế, **instance fields trùng tên** cũng có thể bị hide.

~~~java
class Parent {
    String label = "parent field";
}

class Child extends Parent {
    String label = "child field";
}
~~~

Một Child object có thể chứa **hai instance fields phân biệt**: phần Parent.label kế thừa về mặt trạng thái và Child.label do Child khai báo.

~~~java
Parent view = new Child();
System.out.println(view.label);          // parent field.
System.out.println(((Child) view).label); // child field.
~~~

Runtime object vẫn là Child trong cả hai expressions. Field lookup được xác định **không phải dynamic dispatch**.

### Điều này khác static field ở đâu?

- Với **instance field hiding**, mỗi Child object có phần instance fields tương ứng; đọc Parent.label vs Child.label trên **cùng object** cho hai giá trị khác.
- Với **static field hiding**, các fields thuộc **hai runtime classes**, không phải mỗi object.
- Cả hai đều chọn declaration theo **compile-time qualifier type**.

## 12. Ví dụ chạy: instance field hiding không đa hình

Tạo **`InstanceFieldHidingDemo.java`**:

~~~java
public class InstanceFieldHidingDemo {
    static class Parent {
        String name = "parent";

        String readName() {
            return name;
        }
    }

    static final class Child extends Parent {
        String name = "child";

        @Override
        String readName() {
            return name;
        }
    }

    public static void main(String[] args) {
        Parent p = new Child();
        Child c = (Child) p;

        System.out.println("p.field=" + p.name);
        System.out.println("c.field=" + c.name);
        System.out.println("p.method=" + p.readName());

        p.name = "P2";
        c.name = "C2";

        System.out.println("after p.field=" + p.name);
        System.out.println("after c.field=" + c.name);
        System.out.println("after p.method=" + p.readName());
    }
}
~~~

~~~bash
javac -encoding UTF-8 InstanceFieldHidingDemo.java
java InstanceFieldHidingDemo
~~~

Stdout:

~~~text
p.field=parent
c.field=child
p.method=child
after p.field=P2
after c.field=C2
after p.method=C2
~~~

### Vì sao có hai giá trị field?

`p.name` truy cập field `Parent.name` trong Child object. `c.name` truy cập `Child.name` trong cùng Child object. Khi gọi `p.readName()`, virtual dispatch chọn `Child.readName()`, và body trong Child đọc `Child.name`.

**Không kết luận:** “field nằm trong Child nên p.name sẽ tự dùng Child.name”. Fields không được override. Nếu cần đa hình để truy xuất dữ liệu, hãy cung cấp **method như `name()` và override method**.

## 13. Ép kiểu làm đổi compile-time member lookup, không tạo object khác

~~~java
Parent p = new Child();
System.out.println(p.category());
System.out.println(((Child) p).category());
~~~

Nếu Parent.category và Child.category là static methods cùng chữ ký:

- `p.category()` chọn Parent.category.
- `((Child) p).category()` chọn Child.category.
- Cả hai câu lệnh dùng **cùng runtime object** của p (sau cast).

### Downcast có thể thất bại

~~~java
Parent parentOnly = new Parent();
// Child invalid = (Child) parentOnly; // Biên dịch nhưng ném ClassCastException.
~~~

Cast có runtime check khi cần. Không dùng downcast chỉ để điều khiển việc chọn static method: nếu thực sự muốn gọi Child static method, hãy viết **`Child.category()`**, rõ hơn và không phụ thuộc reference.

### Upcast không xóa khả năng override

~~~java
Parent view = (Parent) new Child();
view.describe();
~~~

Nếu Child override `describe`, virtual call vẫn chạy Child.describe. Cast Parent không “đóng băng” dispatch ở Parent implementation.

## 14. `super.field` và `super.method()`

Trong instance code của Child, có thể dùng `super.field` để truy cập **field khai báo trong superclass** khi field đó accessible.

~~~java
class Parent {
    protected int points = 10;
}

class Child extends Parent {
    private int points = 20;

    int sum() {
        return super.points + this.points;
    }
}
~~~

`super.points` và `this.points` chọn hai fields khác nhau. Với static fields, trong những ngữ cảnh hợp lệ, `super.staticField` có thể được Java chấp nhận về cú pháp, nhưng **nên dùng `Parent.staticField`** để diễn đạt tính class-level.

### `super.instanceMethod()` khác static hiding

Nếu Child override một instance method, `super.method()` trong body Child có thể gọi implementation superclass cụ thể thay vì virtual dispatch quay vào chính Child override.

Với static methods bị hide, dùng `Parent.method()` để gọi rõ superclass static method. Không cần receiver object hay ép kiểu.

### Ví dụ chạy: chọn hai fields bằng `super`

Lưu **`SuperFieldAccessDemo.java`**:

~~~java
public class SuperFieldAccessDemo {
    static class Parent {
        protected int points = 10;
    }

    static final class Child extends Parent {
        private int points = 20;

        int sum() {
            return super.points + this.points;
        }

        String report() {
            return "Parent=" + super.points
                    + ", Child=" + this.points;
        }
    }

    public static void main(String[] args) {
        Child child = new Child();
        System.out.println(child.report());
        System.out.println("sum=" + child.sum());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SuperFieldAccessDemo.java
java SuperFieldAccessDemo
~~~

Stdout:

~~~text
Parent=10, Child=20
sum=30
~~~

Trong cùng Child object tồn tại cả Parent.points và Child.points. Qualifiers `super` và `this` làm rõ declaration cần truy cập.

## 15. Khi nào static method được xem là hiding?

Đối với class hierarchy, một static method trong subclass có thể **hide** một accessible static method tương ứng trong superclass nếu đáp ứng các điều kiện của Java về signatures, name clash, return type, access và checked exceptions.

Ví dụ:

~~~java
class Parent {
    public static Number sample() {
        return 1;
    }
}

class Child extends Parent {
    public static Integer sample() {
        return 2;
    }
}
~~~

`Child.sample()` che `Parent.sample()` với **covariant return type** Integer phù hợp Number. Không có instance method override.

Nhưng không nên cho rằng chỉ cần **hai methods cùng tên** là hiding:

- `sample()` và `sample(int)` là **overloads**, không cùng signature.
- Nếu một method là instance còn method kia static và signatures clash như override/hide, compiler có thể từ chối.
- Hai methods private hoặc inaccessible có những quy tắc inheritance khác, không nên mặc định cùng ý nghĩa hiding.
- Method static `final` của Parent không được hide bằng method cùng signature ở Child theo quy tắc áp dụng.

## 16. Static và instance không thể thay thế nhau như override

Cố ý sai:

~~~java
class Parent {
    static void ping() {}
}

class Child extends Parent {
    // void ping() {} // Lỗi: instance method không thể override/hide static ping.
}
~~~

Chiều ngược lại:

~~~java
class Parent {
    void ping() {}
}

class Child extends Parent {
    // static void ping() {} // Lỗi: static method không thể override instance ping.
}
~~~

Java không cho dùng từ khóa `static` như một cách thay đổi cơ chế dispatch của inherited method cùng signature mà không thay đổi hợp đồng.

### `@Override` đặt trên static method?

~~~java
class Parent {
    static void ping() {}
}

class Child extends Parent {
    // @Override // Lỗi nếu gắn với static ping.
    static void ping() {}
}
~~~

Static `ping` ở Child **hide** static ping ở Parent. Annotation `@Override` không dùng được vì Child.ping không override một instance method.

**Quy ước:** Dùng tên class làm qualifier, không dùng static method như một mechanism của runtime polymorphism.

## 17. Static method hiding và `final`, quyền truy cập

Một method khai báo `final static` không được subclass che khuất với signature trùng theo quy tắc Java:

~~~java
class Parent {
    public static final void stable() {}
}

class Child extends Parent {
    // public static void stable() {} // Không hợp lệ.
}
~~~

Khi Child hide một inherited static method hợp lệ, method mới không được **thu hẹp access** trái quy tắc Java:

~~~java
class Parent {
    public static void show() {}
}

class Child extends Parent {
    // static void show() {} // Lỗi: yếu hơn public.
    public static void show() {}
}
~~~

Ngoài ra return type cần phù hợp, và checked exception declaration bị giới hạn tương tự các quy tắc tương thích cho hiding/overriding. Không nên chỉ đổi tên modifier để bỏ qua compiler.

### Có nên hide public static method của superclass?

Thường **không nên**, nhất là khi method đại diện một “biến thể” của hành vi theo kiểu object. Hãy dùng tên rõ (ví dụ `createCsvFormatter`, `createJsonFormatter`) hoặc một polymorphic instance method.

## 18. Ví dụ chạy: covariant return trong static hiding

Tạo file **`StaticCovariantReturnDemo.java`**:

~~~java
public class StaticCovariantReturnDemo {
    static class Parent {
        public static Number example() {
            return 10;
        }
    }

    static final class Child extends Parent {
        public static Integer example() {
            return 20;
        }
    }

    public static void main(String[] args) {
        Parent parentView = new Child();
        Child childView = (Child) parentView;

        Number a = parentView.example();
        Integer b = childView.example();

        System.out.println("Parent result=" + a);
        System.out.println("Child result=" + b);
        System.out.println("names=" + Parent.example()
                + "/" + Child.example());
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticCovariantReturnDemo.java
java StaticCovariantReturnDemo
~~~

Stdout:

~~~text
Parent result=10
Child result=20
names=10/20
~~~

`Parent.example()` trả Number, Child.example trả Integer phù hợp subtype. Nhưng **lời gọi tĩnh vẫn chọn theo declared reference type**, không có runtime polymorphism.

Một API được thiết kế cho runtime polymorphism nên dùng instance method với covariant return type và `@Override`, không dựa vào static hiding.

## 19. Checked exception constraints khi hiding

Giả sử:

~~~java
class Parent {
    public static String read() throws java.io.IOException {
        return "parent";
    }
}

class Child extends Parent {
    public static String read()
            throws java.io.FileNotFoundException {
        return "child";
    }
}
~~~

Subtype `FileNotFoundException` là checked exception con của `IOException`, nên có thể phù hợp với method ở Parent.

Nhưng Child không thể tùy ý khai báo một checked exception rộng hơn như `throws Exception` khi hide method tương ứng của Parent.

**Tại sao?** Caller được compile dựa trên signature của method được chọn. Contract checked exceptions cần bảo toàn khả năng caller xử lý, kể cả khi static method không virtual dispatch.

Nếu method được gọi qua reference `Parent p`, compile-time method chosen là Parent.read và caller xử lý `IOException` theo declaration ấy, dù actual object là Child.

## 20. Static field hiding không chỉ có primitive fields

Có thể che một reference field:

~~~java
class Parent {
    static String SOURCE = "parent";
}

class Child extends Parent {
    static String SOURCE = "child";
}
~~~

Hai fields giữ hai reference values riêng. Cả String objects đều immutable, nhưng các **field references** không final nên có thể gán lại.

~~~java
Parent.SOURCE = "P2";
Child.SOURCE = "C2";
~~~

Từng assignment đổi field tương ứng. Không có cơ chế đồng bộ hai values chỉ vì cùng field name.

### `static final` cũng có thể bị field hiding

~~~java
class Parent {
    static final int LIMIT = 10;
}

class Child extends Parent {
    static final int LIMIT = 20;
}
~~~

`Parent.LIMIT` và `Child.LIMIT` là hai declarations khác nhau. Field hiding không tự bị cấm bởi `final` trên field. **`final` cấm gán lại chính field**, không cấm subclass khai báo **một field khác cùng tên** theo ngôn ngữ Java trong trường hợp hợp lệ.

Đây là đối lập với **final static method**: method `final` chịu quy tắc cấm hide/override tương ứng.

## 21. Ví dụ chạy: static final constants cùng tên

Tạo file **`StaticFinalFieldHidingDemo.java`**:

~~~java
public class StaticFinalFieldHidingDemo {
    static class Parent {
        static final int LIMIT = 10;
    }

    static final class Child extends Parent {
        static final int LIMIT = 20;
    }

    public static void main(String[] args) {
        Parent p = new Child();
        Child c = (Child) p;

        System.out.println("Parent=" + Parent.LIMIT);
        System.out.println("Child=" + Child.LIMIT);
        System.out.println("p=" + p.LIMIT);
        System.out.println("c=" + c.LIMIT);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticFinalFieldHidingDemo.java
java StaticFinalFieldHidingDemo
~~~

Stdout:

~~~text
Parent=10
Child=20
p=10
c=20
~~~

Hai `LIMIT` là **compile-time constant variables** kiểu int trong ví dụ, nên một số uses có thể được compiler thay bằng constant values. Điều đó càng nhấn mạnh rằng **không có phép tra runtime polymorphic value** khi đọc static field.

Không lấy việc khai báo nhiều constants cùng tên trong hierarchy làm mẫu API được khuyến nghị; qualifier bằng class khai báo sẽ rõ hơn.

## 22. Khi có static method nhưng subclass chỉ muốn hàm tên khác

Trong nhiều dự án, tốt hơn là tránh collision:

~~~java
class ParentTools {
    static String genericName() {
        return "general";
    }
}

class ChildTools extends ParentTools {
    static String specificName() {
        return "specific";
    }
}
~~~

Vì hai methods tên khác nhau, không có hiding của cùng signature. Caller rõ ràng đang yêu cầu công cụ nào.

Tuy nhiên sử dụng `extends` chỉ để lấy các utility static methods của superclass thường không tốt về mô hình is-a. Nếu class chỉ cần dùng helpers, gọi helper bằng tên class hoặc dùng composition, không tạo inheritance hierarchy nhân tạo.

## 23. Truy cập static member qua reference `null`

Một tính chất Java gây bất ngờ:

~~~java
Parent p = null;
System.out.println(p.staticField);
p.staticMethod();
~~~

Với static field/method accessible, Java **không dereference object p như instance member access**, vì static member được chọn theo type. Do đó tham chiếu `p` bằng null trong trường hợp đơn giản **không tự gây `NullPointerException` chỉ vì là null**.

Nhưng **không khuyến nghị** code như vậy: nó khó đọc và có thể khiến người học hiểu sai.

### Trường hợp qualifier expression có side effect

~~~java
factory().staticMethod();
~~~

Java vẫn đánh giá biểu thức `factory()` theo quy tắc ngôn ngữ trước khi lời gọi static được thực hiện, dù **giá trị object** trả về không cần dùng để chọn static method.

Nếu `factory()` in log, cập nhật counter hoặc ném exception, những điều ấy vẫn có thể xảy ra. Không được nói “Java bỏ qua hoàn toàn mọi thứ trước dấu chấm” trong static access qua expression.

## 24. Ví dụ chạy: `null` và side effects của qualifier

Tạo **`NullStaticAccessDemo.java`**:

~~~java
public class NullStaticAccessDemo {
    static class Parent {
        static String label = "PARENT";

        static String describe() {
            return "STATIC";
        }
    }

    static Parent returnNull() {
        System.out.println("qualifier evaluated");
        return null;
    }

    public static void main(String[] args) {
        Parent nothing = null;

        System.out.println("field=" + nothing.label);
        System.out.println("method=" + nothing.describe());

        System.out.println("via call=" + returnNull().label);
        System.out.println("via method=" + returnNull().describe());
    }
}
~~~

~~~bash
javac -encoding UTF-8 NullStaticAccessDemo.java
java NullStaticAccessDemo
~~~

Stdout:

~~~text
field=PARENT
method=STATIC
qualifier evaluated
via call=PARENT
qualifier evaluated
via method=STATIC
~~~

Lời gọi `returnNull()` vẫn chạy và in log mỗi lần. Nhưng việc truy cập static member **không cần dereference null** như instance method hoặc instance field.

### So với instance access

Nếu Parent có method instance `instanceDescribe()`, `nothing.instanceDescribe()` sẽ ném `NullPointerException` khi gọi trong trường hợp thông thường. Đây là khác biệt giữa **static access qua expression qualifier** và **instance access thật sự cần receiver object**.

### Best practice

Viết:

~~~java
System.out.println(Parent.label);
System.out.println(Parent.describe());
~~~

Không viết qua nullable reference; khi code thấy `Parent.`, người đọc biết ngay member thuộc class.

## 25. Static method hiding và class initialization

Static fields/methods gắn với class runtime khai báo. Khi đọc một inherited static field hoặc gọi inherited static method qua **tên subclass**, cần xét **member được khai báo thật ở class nào**, không chỉ qualifier.

Ví dụ:

~~~java
class Parent {
    static int value = 10;
}

class Child extends Parent {
    static int ownValue = 20;
}
~~~

`Child.value` tham chiếu `Parent.value` nếu Child không hide nó. Việc đọc inherited field có thể kích hoạt initialization của **Parent** mà không nhất thiết initialize Child.

Ngược lại, `Child.ownValue` được khai báo trong Child nên khi dùng sẽ kích hoạt initialization Child nếu chưa initialized, theo quy tắc class initialization.

### Compile-time constants là trường hợp riêng

`static final int LIMIT = 10` với constant expression là **constant variable**. Việc đọc giá trị hằng theo cách thông thường có thể không kích hoạt class initialization. Không được dùng mọi constant value access để chứng minh static blocks đã chạy.

## 26. Ví dụ chạy: class khai báo static member quyết định initialization

Tạo **`StaticOwnerInitializationDemo.java`**:

~~~java
public class StaticOwnerInitializationDemo {
    static class Parent {
        static final int COMPILE_TIME_LIMIT = 7;

        static int inherited = 10;

        static {
            System.out.println("Parent initialized");
        }
    }

    static final class Child extends Parent {
        static int own = 20;

        static {
            System.out.println("Child initialized");
        }
    }

    public static void main(String[] args) {
        System.out.println("constant=" + Child.COMPILE_TIME_LIMIT);
        System.out.println("inherited=" + Child.inherited);
        System.out.println("own=" + Child.own);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticOwnerInitializationDemo.java
java StaticOwnerInitializationDemo
~~~

Stdout:

~~~text
constant=7
Parent initialized
inherited=10
Child initialized
own=20
~~~

Giải thích:

1. `COMPILE_TIME_LIMIT` là constant variable của Parent, nên đọc bằng `Child.COMPILE_TIME_LIMIT` trong ví dụ không làm Parent/Child static blocks chạy.
2. `Child.inherited` thực chất là non-constant static field **Parent.inherited**. Lần đọc làm Parent initialization chạy, in `Parent initialized`; Child chưa cần được initialize.
3. `Child.own` là static field do Child khai báo, khiến Child initialize, in `Child initialized`. Parent đã initialized nên không chạy lại.

**Bài học:** Qua inheritance, cú pháp `Child.member` không đủ để xác định initialization owner; phải biết **member được khai báo ở đâu**.

## 27. Class loader và static state: giới hạn của “dùng chung”

Trong chương trình đơn giản, `Parent.counter` là một static field chung của mọi code dùng **cùng Parent runtime class**. Nhưng class identity ở JVM có thể phụ thuộc class loader; hai class loaders khác nhau có thể định nghĩa hai runtime classes cùng tên với static states riêng.

Điều đó không thay đổi quy tắc field hiding. Nó chỉ nhắc rằng “chỉ có một field static duy nhất trong toàn bộ JVM dù có bao nhiêu class loaders” là một phát biểu quá mức.

Trong hệ thống có plugins, app servers hoặc isolated test loaders, cần xét **runtime class identity** và context loading trước khi so sánh “Parent.staticField này” với “Parent.staticField kia”.

Không cần custom class loader để học bài; đây là giới hạn quan trọng khi đem kiến thức áp dụng vào hệ thống lớn.

## 28. Không nhầm hiding với overloading

**Static method overloading**:

~~~java
class Printer {
    static void print(int value) {
        System.out.println("int: " + value);
    }

    static void print(String value) {
        System.out.println("String: " + value);
    }
}
~~~

Hai static methods cùng tên nhưng **khác parameter list**, nên là overloads trong một class.

**Static method hiding**:

~~~java
class Parent {
    static String identify() {
        return "Parent";
    }
}

class Child extends Parent {
    static String identify() {
        return "Child";
    }
}
~~~

Hai methods trong class hierarchy có **cùng chữ ký**. Child declaration hide Parent declaration theo quy tắc Java.

### Overload selection dựa trên compile-time argument types

~~~java
static String show(Object value) {
    return "Object";
}

static String show(String value) {
    return "String";
}
~~~

Nếu một biến `Object value = "text";`, lời gọi `show(value)` thường chọn overload `show(Object)`; runtime value String không tự chuyển overload thành `show(String)`.

Đây cũng là chọn tại compile time, nhưng là **overload resolution** chứ không phải **field/static hiding**. Không gộp hai thuật ngữ.

## 29. Ví dụ chạy: overloading kết hợp instance overriding

Lưu **`OverloadVsOverrideDemo.java`**:

~~~java
public class OverloadVsOverrideDemo {
    static class Parent {
        String accept(Object value) {
            return "Parent Object";
        }

        String accept(String value) {
            return "Parent String";
        }
    }

    static final class Child extends Parent {
        @Override
        String accept(Object value) {
            return "Child Object";
        }

        @Override
        String accept(String value) {
            return "Child String";
        }
    }

    public static void main(String[] args) {
        Parent receiver = new Child();

        Object asObject = "java";
        String asString = "java";

        System.out.println(receiver.accept(asObject));
        System.out.println(receiver.accept(asString));
    }
}
~~~

~~~bash
javac -encoding UTF-8 OverloadVsOverrideDemo.java
java OverloadVsOverrideDemo
~~~

Stdout:

~~~text
Child Object
Child String
~~~

Hai bước:

1. Compiler chọn **`accept(Object)` hoặc `accept(String)`** theo compile-time argument type.
2. Runtime dispatch chọn **Child implementation** của đúng method signature đã chọn, vì receiver thực sự là Child.

Khi đối chiếu với static method hiding, hãy nhớ: **runtime dispatch chỉ áp dụng sau khi đã xác định một instance method invocation phù hợp**, không được dùng để chọn overload dựa trên runtime argument class.

## 30. Static overloads trong class hierarchy

Giả sử:

~~~java
class Parent {
    static String format(Object value) {
        return "Parent Object";
    }
}

class Child extends Parent {
    static String format(String value) {
        return "Child String";
    }
}
~~~

`Child.format(String)` không hide `Parent.format(Object)` vì signatures khác nhau; đây là overload khác. Khi `Child.format(...)`, cả hai candidates có thể tham gia overload resolution tùy ngữ cảnh/access.

Nếu caller tham chiếu theo type Parent, Child-only static overload không tự có mặt trong compile-time method set của Parent.

### Chương trình chạy

Lưu **`StaticOverloadHierarchyDemo.java`**:

~~~java
public class StaticOverloadHierarchyDemo {
    static class Parent {
        static String format(Object value) {
            return "Parent Object";
        }
    }

    static final class Child extends Parent {
        static String format(String value) {
            return "Child String";
        }
    }

    public static void main(String[] args) {
        Object textAsObject = "java";

        System.out.println(Parent.format("java"));
        System.out.println(Child.format("java"));
        System.out.println(Child.format(textAsObject));
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticOverloadHierarchyDemo.java
java StaticOverloadHierarchyDemo
~~~

Stdout:

~~~text
Parent Object
Child String
Parent Object
~~~

`Child.format("java")` chọn overload cụ thể hơn cho String. `Child.format(textAsObject)` chọn Parent.format(Object), vì compile-time argument type là Object. Không có runtime “thử lại” overload bằng String.

## 31. Phương thức instance là lựa chọn đúng khi cần đa hình

Nếu yêu cầu: “Cùng method `label()` trên một Parent reference phải trả label theo loại object thực”, hãy dùng **instance method**.

~~~java
class Animal {
    String label() {
        return "animal";
    }
}

class Dog extends Animal {
    @Override
    String label() {
        return "dog";
    }
}
~~~

~~~java
Animal a = new Dog();
System.out.println(a.label()); // dog.
~~~

Đây là các mảnh minh họa.

Ngược lại nếu viết `static String label()` ở cả hai classes, `a.label()` sẽ chọn Animal.label, không phải Dog.label. Static method không phù hợp để mô tả state hoặc hành vi theo **runtime subtype**.

### Chương trình chạy: bản thiết kế polymorphic đúng

Tạo **`PolymorphicLabelDemo.java`**:

~~~java
public class PolymorphicLabelDemo {
    static class Animal {
        String label() {
            return "animal";
        }
    }

    static final class Dog extends Animal {
        @Override
        String label() {
            return "dog";
        }
    }

    static final class Cat extends Animal {
        @Override
        String label() {
            return "cat";
        }
    }

    static void print(Animal animal) {
        System.out.println("label=" + animal.label());
    }

    public static void main(String[] args) {
        print(new Dog());
        print(new Cat());
    }
}
~~~

~~~bash
javac -encoding UTF-8 PolymorphicLabelDemo.java
java PolymorphicLabelDemo
~~~

Stdout:

~~~text
label=dog
label=cat
~~~

`print(Animal)` không phụ thuộc vào concrete classes Dog/Cat. Đây mới là **runtime subtype polymorphism**. Không cần static field cùng tên hay cast.

## 32. Static factories: có thể hide nhưng thường nên dùng tên rõ

Java có nhiều **static factory methods** như `of(...)`, `from(...)`, `valueOf(...)`. Một superclass và subclass có thể khai báo những static factories cùng chữ ký, nhưng static method không dispatch polymorphically theo receiver object.

Ví dụ:

~~~java
class Parent {
    static Parent create() {
        return new Parent();
    }
}

class Child extends Parent {
    static Child create() {
        return new Child();
    }
}
~~~

Gọi `Parent.create()` tạo Parent, `Child.create()` tạo Child theo từng method body. Một biến Parent tham chiếu Child **không làm** `ref.create()` chọn Child.create.

Nếu API cần tạo subtype từ cấu hình, cân nhắc:

- Factory interface/strategy instance và dynamic dispatch.
- Registry có explicit type key.
- Factory method tên rõ và class qualifier.
- Constructor injection hoặc dependency injection.

Không ép design phải dùng inheritance chỉ để tạo một “static factory đa hình” mà ngôn ngữ không hỗ trợ.

## 33. Ví dụ chạy: static factory hiding

Tạo **`StaticFactoryHidingDemo.java`**:

~~~java
public class StaticFactoryHidingDemo {
    static class Parent {
        static Parent create() {
            return new Parent();
        }

        String name() {
            return "Parent instance";
        }
    }

    static final class Child extends Parent {
        static Child create() {
            return new Child();
        }

        @Override
        String name() {
            return "Child instance";
        }
    }

    public static void main(String[] args) {
        Parent parentView = new Child();

        Parent createdViaView = parentView.create();
        Parent createdViaChildClass = Child.create();

        System.out.println("via view=" + createdViaView.name());
        System.out.println("via class=" + createdViaChildClass.name());
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticFactoryHidingDemo.java
java StaticFactoryHidingDemo
~~~

Stdout:

~~~text
via view=Parent instance
via class=Child instance
~~~

Khi `parentView.create()` được giải theo compile-time Parent, nó gọi Parent.create và tạo Parent instance mới. `Child.create()` tạo Child instance mới. Sau đó `name()` được gọi như một **instance virtual method**, nên trả theo class của object mới tương ứng.

### Hai cơ chế trong cùng chương trình

- **Static factory selection:** compile-time.
- **Virtual `name()` dispatch:** runtime.

Không đồng nhất hai mốc quyết định.

## 34. Interface constants có thể bị class field che tên

Một interface field mặc nhiên là **`public static final`**:

~~~java
interface Flags {
    String LABEL = "interface";
}
~~~

Một class implementing interface có thể khai báo field cùng tên:

~~~java
class Item implements Flags {
    static String LABEL = "class";
}
~~~

Cú pháp qualified:

~~~java
System.out.println(Flags.LABEL); // interface.
System.out.println(Item.LABEL);  // class.
~~~

Nếu một biến được khai báo kiểu `Flags`:

~~~java
Flags asInterface = new Item();
System.out.println(asInterface.LABEL); // interface.
~~~

Static field access tiếp tục theo **compile-time type**.

**Không khuyến nghị** đọc interface constants qua object references. Dùng `Flags.LABEL` để tránh người đọc tưởng field thuộc về từng Item instance.

## 35. Ví dụ chạy: interface constant và class field hiding

Lưu **`InterfaceFieldHidingDemo.java`**:

~~~java
public class InterfaceFieldHidingDemo {
    interface HasLabel {
        String LABEL = "interface";
    }

    static final class Item implements HasLabel {
        static final String LABEL = "class";
    }

    public static void main(String[] args) {
        HasLabel asInterface = new Item();
        Item asClass = (Item) asInterface;

        System.out.println("interface=" + HasLabel.LABEL);
        System.out.println("class=" + Item.LABEL);
        System.out.println("via interface=" + asInterface.LABEL);
        System.out.println("via class=" + asClass.LABEL);
    }
}
~~~

~~~bash
javac -encoding UTF-8 InterfaceFieldHidingDemo.java
java InterfaceFieldHidingDemo
~~~

Stdout:

~~~text
interface=interface
class=class
via interface=interface
via class=class
~~~

Một Item object không làm interface field trở thành instance field. Hai constant declarations tồn tại ở hai types và cú pháp qua interface/class quyết định field được chọn.

## 36. Static methods của interface không được thừa hưởng như class static methods

Java cho phép interface khai báo static methods:

~~~java
interface Tools {
    static String format() {
        return "Tools";
    }
}
~~~

Một class:

~~~java
class Service implements Tools {
}
~~~

**không được thừa hưởng** `Tools.format()` theo cách static method khai báo ở superclass có thể được truy cập qua subclass. Gọi:

~~~java
Tools.format();
~~~

Không viết `Service.format()` trừ khi Service **tự khai báo một static method** tên ấy. Nếu Service tự khai báo, đó là method của Service, không phải một runtime override của interface static method.

### Ví dụ chạy

Tạo **`InterfaceStaticMethodsDemo.java`**:

~~~java
public class InterfaceStaticMethodsDemo {
    interface Tools {
        static String format() {
            return "interface Tools";
        }
    }

    static final class Service implements Tools {
        static String format() {
            return "class Service";
        }
    }

    public static void main(String[] args) {
        System.out.println(Tools.format());
        System.out.println(Service.format());
    }
}
~~~

~~~bash
javac -encoding UTF-8 InterfaceStaticMethodsDemo.java
java InterfaceStaticMethodsDemo
~~~

Stdout:

~~~text
interface Tools
class Service
~~~

Không gọi `Service.format()` là “override `Tools.format()`”. Interface static methods được khai báo cho interface itself và không inherited vào Service; hai methods ở ví dụ là những declarations khác nhau.

### Default methods thì khác

Interface `default` methods là instance methods có body. Class implementing interface có thể override chúng và runtime dispatch theo actual object. Đừng gộp default method overriding với static method hiding chỉ vì cả hai được khai báo trong interface.

## 37. Xung đột tên field từ hai interfaces

Nếu class implements hai interfaces có cùng constant name:

~~~java
interface Left {
    int VALUE = 1;
}

interface Right {
    int VALUE = 2;
}

class Both implements Left, Right {
}
~~~

Tham chiếu đơn `VALUE` trong class Both có thể **ambiguous** vì cả Left.VALUE và Right.VALUE đều là candidates. Dùng qualified names:

~~~java
int sum = Left.VALUE + Right.VALUE;
~~~

Một class có thể tự khai báo field `VALUE` để che những declarations tương ứng theo quy tắc, nhưng điều đó thường làm API khó hiểu hơn.

Đừng coi interface constants là polymorphic configuration mechanism. Nếu muốn lấy giá trị khác nhau theo implementing object, khai báo một **instance method như `int value()`** và implement/override.

## 38. Visibility: field private không giống protected/public hiding

Một private field của Parent không được subclass truy cập bằng tên như một inherited public/protected field. Subclass có thể khai báo field riêng cùng tên mà không “override” field private.

~~~java
class Parent {
    private int id = 1;

    public int parentId() {
        return id;
    }
}

class Child extends Parent {
    private int id = 2;

    public int childId() {
        return id;
    }
}
~~~

`Parent.parentId()` đọc private Parent.id; `Child.childId()` đọc private Child.id. Không phải một field mutable đa hình duy nhất.

### Ví dụ chạy

Lưu **`PrivateFieldNamesDemo.java`**:

~~~java
public class PrivateFieldNamesDemo {
    static class Parent {
        private final int id = 1;

        public int parentId() {
            return id;
        }
    }

    static final class Child extends Parent {
        private final int id = 2;

        public int childId() {
            return id;
        }
    }

    public static void main(String[] args) {
        Child c = new Child();
        System.out.println("parentId=" + c.parentId());
        System.out.println("childId=" + c.childId());
    }
}
~~~

~~~bash
javac -encoding UTF-8 PrivateFieldNamesDemo.java
java PrivateFieldNamesDemo
~~~

Stdout:

~~~text
parentId=1
childId=2
~~~

Do methods xác định access context riêng của class khai báo, hai getters đọc hai fields riêng. Đây cũng là ví dụ tại sao nên giữ state private và cung cấp behavior có nghĩa hơn là trông đợi field đa hình.

## 39. Shadowing bởi local variable khác field hiding

Ví dụ:

~~~java
class Counter {
    private int value;

    void update(int value) {
        this.value = value;
    }
}
~~~

Ở method `update`, parameter `value` **shadow** instance field `value`. `this.value` dùng để truy cập field của object, còn `value` bên phải là parameter.

Không gọi đây là “static method hiding” hoặc “subclass field hiding” vì không có class hierarchy nào ở phép tra tên này. Từ **shadowing** rộng hơn và liên quan scope khác.

### Khi class con khai báo field cùng tên parameter?

Phải xét scope trong từng biểu thức. Parameter/local variable có thể che tên field, `this` có thể chọn field hiện tại, `super` có thể chọn field superclass. Vấn đề không phải duy nhất một luật “tên nào ở gần nhất” cho mọi case; hãy ghi rõ **loại declaration và ngữ cảnh access**.

## 40. Static hiding không phụ thuộc biến có thật được tạo không

Bạn có thể gọi:

~~~java
Parent.identify();
Child.identify();
~~~

trước khi tạo **bất kỳ Parent/Child instance nào**, nếu methods accessible và class initialization cho phép. Static members thuộc class, không cần receiver object.

Đối với dynamic polymorphism:

~~~java
Parent parent = new Child();
parent.describe();
~~~

cần một reference trỏ actual object để thực hiện instance method invocation. `new Child()` tạo object và các instance fields/constructors được thực thi theo quy tắc.

Sự khác nhau giải thích vì sao một static method không thể “tự đoán runtime subtype đang muốn gọi” nếu không có explicit argument/type key.

## 41. Design smell: “định nghĩa đa hình” bằng static fields

Phản ví dụ:

~~~java
class Animal {
    static String TYPE = "animal";
}

class Dog extends Animal {
    static String TYPE = "dog";
}

class Cat extends Animal {
    static String TYPE = "cat";
}
~~~

Nếu code nhận `Animal animal`, `animal.TYPE` luôn được phân giải theo Animal, bất kể object Dog/Cat. Đây thường không phải điều mong muốn.

### Cải thiện bằng instance behavior

~~~java
abstract class Animal {
    abstract String type();
}

class Dog extends Animal {
    @Override
    String type() {
        return "dog";
    }
}

class Cat extends Animal {
    @Override
    String type() {
        return "cat";
    }
}
~~~

Khi đó `Animal a = new Dog(); a.type()` trả `"dog"`. Code hoạt động theo runtime subtype đúng như contract.

Một giải pháp khác là lưu type value trong instance field có constructor validation nếu subtype hierarchy không cần thiết. Điều quan trọng là **chọn data model theo use case**, không dùng static field để mô phỏng per-object polymorphism.

## 42. Design smell: static service method “được override” ở subclass

Một codebase có thể viết:

~~~java
class BaseFormatter {
    static String format(Object input) {
        return "base";
    }
}

class JsonFormatter extends BaseFormatter {
    static String format(Object input) {
        return "json";
    }
}
~~~

Rồi hy vọng `BaseFormatter f = new JsonFormatter(); f.format(data)` gọi JsonFormatter. Điều đó **sai**: compiler chọn BaseFormatter.format.

Nếu service phải hoán đổi implementation tại runtime, dùng interface:

~~~java
interface Formatter {
    String format(Object input);
}

class JsonFormatter implements Formatter {
    @Override
    public String format(Object input) {
        return "json";
    }
}
~~~

Đây là những đoạn minh họa. Caller có thể nhận `Formatter` trong constructor và gọi instance method. Không nhất thiết subclass một utility class chỉ để “hưởng” static helpers.

## 43. Ví dụ chạy: refactor static hiding thành instance strategy

Lưu file **`StrategyInsteadOfStaticHidingDemo.java`**:

~~~java
public class StrategyInsteadOfStaticHidingDemo {
    interface Formatter {
        String format(String value);
    }

    static final class PlainFormatter implements Formatter {
        @Override
        public String format(String value) {
            return value;
        }
    }

    static final class BracketFormatter implements Formatter {
        @Override
        public String format(String value) {
            return "[" + value + "]";
        }
    }

    static void show(Formatter formatter) {
        System.out.println(formatter.format("Java"));
    }

    public static void main(String[] args) {
        show(new PlainFormatter());
        show(new BracketFormatter());
    }
}
~~~

~~~bash
javac -encoding UTF-8 StrategyInsteadOfStaticHidingDemo.java
java StrategyInsteadOfStaticHidingDemo
~~~

Stdout:

~~~text
Java
[Java]
~~~

Lời gọi `show(Formatter)` phụ thuộc vào interface contract, và runtime object quyết định implementation. Đây là đa hình thực sự, khác việc chọn static member bằng tên class/declared reference type.

## 44. Generic classes vẫn không nhân bản static fields theo type arguments

Xét:

~~~java
class Box<T> {
    static int created;

    Box() {
        created++;
    }
}
~~~

`Box<String>` và `Box<Integer>` không có **hai static counters riêng** chỉ vì type arguments khác nhau. Generic type arguments trong Java chịu cơ chế type erasure; static field thuộc Box runtime class.

### Ví dụ chạy

Lưu **`GenericStaticFieldDemo.java`**:

~~~java
public class GenericStaticFieldDemo {
    static final class Box<T> {
        private static int created;

        Box(T value) {
            created++;
        }

        static int created() {
            return created;
        }
    }

    public static void main(String[] args) {
        Box<String> word = new Box<>("Java");
        Box<Integer> number = new Box<>(17);

        System.out.println("word type=" + word.getClass().getSimpleName());
        System.out.println("number type=" + number.getClass().getSimpleName());
        System.out.println("created=" + Box.created());
    }
}
~~~

~~~bash
javac -encoding UTF-8 GenericStaticFieldDemo.java
java GenericStaticFieldDemo
~~~

Stdout:

~~~text
word type=Box
number type=Box
created=2
~~~

Không có hiding trong đoạn này; nó giải thích **scope của static field** khi class generic được sử dụng với nhiều type arguments. Trong thực tế compiler không cho một static field của generic class trực tiếp dùng type parameter `T` làm kiểu: `static T value;` không hợp lệ, vì static context không gắn riêng với mỗi type instantiation.

## 45. Reflection: khai báo field nào khác với lookup tiện dụng

Nếu dùng reflection, một class có thể có field khai báo trong chính nó và một field cùng tên khai báo ở superclass. Có thể cần phân biệt `getDeclaredField` trên từng Class object thay vì nghĩ “đọc field theo tên luôn là một field duy nhất”.

Ví dụ:

~~~java
java.lang.reflect.Field parentField =
        Parent.class.getDeclaredField("value");
java.lang.reflect.Field childField =
        Child.class.getDeclaredField("value");
~~~

Các dòng trên là mã minh họa; nếu class Parent/Child thực sự khai báo `value`, hai Field objects đại diện hai member declarations khác nhau. `getDeclaredField` có checked exception `NoSuchFieldException` cần xử lý hoặc khai báo throws.

### Vì sao không dùng reflection làm lối tắt học static hiding?

Reflection còn có visibility/access checks, lookup APIs và cơ chế gọi khác với cú pháp Java thông thường. Để học quy tắc hiding, **dùng trực tiếp `Parent.value`, `Child.value` và declared reference types** sẽ rõ hơn. Reflection chỉ có ích khi phát triển frameworks hoặc tooling cần inspect member declarations.

## 46. Bài test cần xác nhận cả compile-time và runtime paths

Khi thiết kế tests cho hierarchy:

1. Gán object Child vào biến kiểu Parent.
2. Truy cập field static qua Parent và Child qualifiers.
3. Gọi static methods qua Parent/Child qualifiers.
4. Gọi methods instance được override qua Parent reference.
5. Downcast hợp lệ rồi truy cập lại field/static method.
6. Thử tình huống inherited member không bị hide.
7. Thử field bị che khuất có giá trị khác.
8. Kiểm tra static owner initialization nếu code có side effects.
9. Kiểm tra semantics cần đa hình thật, để đảm bảo không vô tình dùng static.
10. Không dựa vào order của test methods hoặc mutable global static state.

**Không nhất thiết chạy test framework bên ngoài** để xác nhận những semantics cơ bản: các chương trình `main` với stdout trong README đã minh họa. Với ứng dụng thật, có thể đưa expectations vào JUnit assertions.

## 47. Bài tập 1 — Dự đoán output static và instance

Cho:

~~~java
class A {
    static String s() {
        return "A static";
    }

    String i() {
        return "A instance";
    }
}

class B extends A {
    static String s() {
        return "B static";
    }

    @Override
    String i() {
        return "B instance";
    }
}
~~~

Caller:

~~~java
A x = new B();
System.out.println(x.s());
System.out.println(x.i());
System.out.println(B.s());
~~~

**Đáp án:**

~~~text
A static
B instance
B static
~~~

`x.s()` chọn A.s theo compile-time type A. `x.i()` dispatch đến B.i vì runtime receiver B. `B.s()` gọi rõ method của B.

## 48. Bài tập 2 — Hai static fields riêng

~~~java
class A {
    static int n = 1;
}

class B extends A {
    static int n = 2;
}
~~~

Sau:

~~~java
A.n += 5;
B.n += 10;
System.out.println(A.n);
System.out.println(B.n);
~~~

**Đáp án:**

~~~text
6
12
~~~

Hai fields khác nhau. Đừng nhầm việc dùng tên `n` giống nhau với việc dùng chung storage.

## 49. Bài tập 3 — Không khai báo field mới

~~~java
class A {
    static int n = 1;
}

class B extends A {
}
~~~

Sau:

~~~java
B.n = 8;
System.out.println(A.n);
~~~

**Đáp án:** `8`, vì `B.n` là inherited field **A.n**, không phải field mới trong B.

## 50. Bài tập 4 — Ép kiểu Parent ↔ Child

~~~java
A a = new B();
System.out.println(a.n);
System.out.println(((B) a).n);
~~~

Giả sử A.n=3 và B.n=9.

**Đáp án:**

~~~text
3
9
~~~

Cast thay compile-time type của field access expression. Runtime object vốn đã B, không có object mới được tạo. Nếu actual object không phải B, cast B có thể ném ClassCastException.

## 51. Bài tập 5 — Interface static method có inherited không?

~~~java
interface I {
    static void work() {
        System.out.println("I");
    }
}

class C implements I {
}
~~~

**Đáp án:** `I.work()` hợp lệ. `C.work()` không được thừa hưởng chỉ do implements I. Nếu C tự khai báo `static void work()`, nó là method của C, không là instance overriding của I.work.

## 52. Bài tập 6 — Kết hợp field hiding, method overriding

~~~java
class Parent {
    int value = 1;

    int getValue() {
        return value;
    }
}

class Child extends Parent {
    int value = 2;

    @Override
    int getValue() {
        return value;
    }
}
~~~

Nếu `Parent p = new Child();`:

**Đáp án:** `p.value == 1`, còn `p.getValue() == 2`. Field lookup dựa vào Parent compile-time type; virtual method gọi Child override.

## 53. Bài tập 7 — Sai ở đâu với `@Override`?

~~~java
class Parent {
    static void ping() {}
}

class Child extends Parent {
    // @Override
    static void ping() {}
}
~~~

Nếu bật annotation, compiler từ chối vì method static Child.ping **hide**, không override. Đừng sửa thành một instance method cùng chữ ký: static/instance clash vẫn lỗi. Nếu cần polymorphism, tạo method instance trong Parent và override đúng.

## 54. Bài tập 8 — Hai static final constants

~~~java
class P {
    static final String KIND = "P";
}
class C extends P {
    static final String KIND = "C";
}
~~~

`P ref = new C();` thì `ref.KIND` là `"P"`. Nếu ép `((C) ref).KIND` thì `"C"`. Đây là hai constant variables độc lập, không có object-level polymorphism.

## 55. Bài tập 9 — Truy cập static qua null

Cho:

~~~java
class Tool {
    static String name() {
        return "utility";
    }
}

Tool ref = null;
System.out.println(ref.name());
~~~

**Đáp án:** In `utility` trong ngữ cảnh Java hợp lệ. Không có dereference instance trong lời gọi static ấy. Tuy nhiên viết `Tool.name()` là cách đúng phong cách và không gây nhầm.

Nếu qualifier là lời gọi method có side effect như `getNull().name()`, Java vẫn đánh giá `getNull()` trước khi thực hiện static method invocation.

## 56. Bài tập 10 — Chọn design theo mục đích

Một thư viện có `Animal` và `Dog`; yêu cầu `displayName(Animal a)` trả tên phụ thuộc runtime subtype. Hai đề xuất:

- Đặt `static String TYPE` trong mỗi subclass.
- Khai báo `String type()` instance method trong Animal và override ở subclasses.

**Đáp án:** Dùng instance method nếu mục tiêu là runtime polymorphism. Static fields chọn theo compile-time type của reference, không cho kết quả tùy runtime subtype.

## 57. Những sai lầm thường gặp

| Hiểu lầm | Điều đúng |
| --- | --- |
| “Static method ở subclass override Parent.” | Nó **hide** khi cùng signature phù hợp. |
| “`@Override` dùng cho mọi method cùng tên.” | Không dùng annotation cho static hiding. |
| “Một object Child thì `Parent ref` luôn đọc Child fields.” | Fields chọn theo declared reference type. |
| “Field hiding có dynamic dispatch.” | Không; field lookup khác instance method dispatch. |
| “Tạo Child sẽ tạo một bản Parent static field mới.” | Không; nếu không khai báo lại, field static vẫn thuộc Parent. |
| “Cùng field name nghĩa cùng storage.” | Hai declarations có thể là hai fields riêng. |
| “`final static field` không thể bị class con khai báo field cùng tên.” | Field final và field hiding là hai vấn đề khác; hiding có thể hợp lệ. |
| “Static `final` method có thể hide tùy ý.” | Final method không được hide/override theo quy tắc liên quan. |
| “Static method được chọn theo runtime object.” | Không; chọn tại compile time. |
| “Ép kiểu Parent làm Child trở thành Parent object.” | Không; cast không tạo/cắt object. |
| “`null.staticMethod()` luôn ném NPE.” | Không nếu đó là static member access hợp lệ, dù qualifier expression vẫn được đánh giá. |
| “Mọi thứ sau dấu chấm bị bỏ qua khi truy cập static.” | Qualifier expression có thể gây side effects. |
| “Truy cập `Child.parentField` luôn initialize Child.” | Inherited static member có thể chỉ initialize class khai báo Parent. |
| “Đọc compile-time constant chắc chắn chạy static block.” | Không nhất thiết; constant variable có quy tắc đặc biệt. |
| “Static interface method inherited vào implements class.” | Interface static methods không inherited như class static methods. |
| “`List<Child>` là `List<Parent>` vì Child extends Parent.” | Java generics invariant, không tự suy ra như vậy. |
| “Overloading và hiding đều do runtime subclass quyết định.” | Overload/static hiding dựa vào compile-time contexts. |
| “`super.field` và `this.field` luôn một field.” | Khi có hiding, đó có thể là hai declarations khác nhau. |
| “Fields cùng tên là cách chuẩn để cấu hình subtype.” | Dùng polymorphic instance behavior hoặc explicit config. |
| “Static factory gọi qua Parent ref tạo Child vì ref đang giữ Child.” | Static factory selection không dùng dynamic dispatch. |

## 58. Checklist cuối bài

- [ ] Tôi biết declared type và runtime class có thể khác nhau.
- [ ] Tôi hiểu Child object có thể được giữ bằng Parent reference.
- [ ] Tôi phân biệt field hiding với instance method overriding.
- [ ] Tôi biết static method hiding khác overriding.
- [ ] Tôi gọi static members bằng `ClassName.member` thay vì object qualifier.
- [ ] Tôi hiểu `Parent ref = new Child(); ref.staticField` chọn Parent field.
- [ ] Tôi hiểu `ref.staticMethod()` chọn Parent static method.
- [ ] Tôi hiểu `ref.instanceMethod()` dispatch theo actual Child nếu override.
- [ ] Tôi biết cast có thể đổi compile-time field/static lookup.
- [ ] Tôi không nghĩ upcast tạo/cắt object.
- [ ] Tôi hiểu hai static fields cùng tên có thể lưu hai values độc lập.
- [ ] Tôi biết inherited static field không tạo bản mới ở subclass.
- [ ] Tôi biết instance fields cũng có thể bị hiding.
- [ ] Tôi dùng `super.field` và `this.field` để phân biệt declarations khi thích hợp.
- [ ] Tôi biết `@Override` không hợp lệ cho static method hiding.
- [ ] Tôi nhận biết sai lầm static/instance method cùng signature clash.
- [ ] Tôi biết static final method khác static final field ở khả năng hiding.
- [ ] Tôi biết quyền truy cập, return type và checked exceptions phải tương thích.
- [ ] Tôi hiểu static member access qua null qualifier có thể hợp lệ.
- [ ] Tôi hiểu qualifier expression vẫn có thể chạy side effects.
- [ ] Tôi phân biệt static hiding với overload resolution.
- [ ] Tôi biết instance override được dynamic dispatch sau overload selection.
- [ ] Tôi hiểu inherited static member được gắn với class khai báo khi initialization.
- [ ] Tôi nhận diện compile-time constant access có thể không initialize class.
- [ ] Tôi biết interface constants được chọn theo compile-time type.
- [ ] Tôi biết interface static methods không inherited vào class.
- [ ] Tôi biết generic type arguments không tạo bản static field riêng.
- [ ] Tôi có thể refactor từ static hiding sang polymorphic instance method.
- [ ] Tôi kiểm thử được cả member lookup lẫn runtime dispatch.
- [ ] Tôi giải thích được stdout các chương trình Java 17+ trong bài.

**Kết luận:** **Hiding** không phải **overriding**. Khi subclass khai báo field cùng tên, Java có thể có **hai field declarations** và việc truy cập chọn field theo **compile-time type**. Khi subclass khai báo static method tương ứng, nó **che** method static của superclass, nên lời gọi cũng chọn theo type ở compile time, không theo actual receiver. Ngược lại, một **instance method được override** sẽ được dispatch theo runtime class của object. Hiểu ba đường chọn member này giúp dự đoán output, giải thích chính xác chuyện upcasting và tránh thiết kế “đa hình” giả bằng static fields/static methods. Nếu mục tiêu là thay đổi hành vi theo object thực tế, hãy dùng **instance methods/interfaces/strategies** thay vì static hiding.
