# Thành viên được kế thừa và giới hạn của thành viên `private` trong Java

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **thành viên của một lớp**, **thành viên được lớp con kế thừa**, **thành viên được lớp con khai báo riêng** và **thành viên lớp cha mà lớp con không có quyền truy cập trực tiếp**.
- Giải thích vai trò của các mức truy cập `public`, `protected`, *package-private* (không viết modifier) và `private` trong kế thừa Java.
- Hiểu vì sao một đối tượng `Child` có **trạng thái riêng của `Parent`**, kể cả khi field đó là `private`, nhưng code trong Child không được đọc/ghi field bằng tên trực tiếp.
- Nắm quy tắc **constructor không được kế thừa**, việc dùng `super(...)` và trường hợp constructor của superclass không accessible.
- Phân biệt **overriding** instance methods, **hiding** static methods và fields, với trường hợp **private method không thể bị override**.
- Hiểu rằng phương thức cùng chữ ký khai báo trong Child với private method trong Parent là **phương thức mới**, không phải một override của phương thức private đó.
- Phân tích khác biệt giữa **truy cập `protected` ở cùng package và khác package**, đặc biệt quy tắc kiểu của biểu thức receiver trong subclass ở package khác.
- Hiểu inheritance của members trong class và interface, bao gồm instance default methods, static interface methods và private interface helpers trong Java 17.
- Viết thiết kế lớp cha bảo vệ invariants bằng private state, public/protected methods có hợp đồng, hạn chế lộ mutable fields cho subclasses.
- Đọc, biên dịch và chạy chương trình Java 17+ với output chính xác; nhận diện các lỗi compile-time cần tránh.

## 1. Kế thừa không phải sao chép toàn bộ mã nguồn cha vào con

Một class có thể kế thừa class khác bằng `extends`:

~~~java
class Animal {
    public void eat() {
        System.out.println("eating");
    }
}

class Dog extends Animal {
    public void bark() {
        System.out.println("woof");
    }
}
~~~

Trong method phù hợp, `new Dog().eat()` là lời gọi hợp lệ. `Dog` có thể dùng public method `eat` do `Animal` khai báo theo quy tắc inheritance/accessibility. Nhưng `Dog` không có một bản copy source code riêng của `eat`.

Trong Java, *kế thừa* là quan hệ **kiểu và thành viên** do ngôn ngữ định nghĩa, không phải thao tác copy-paste fields và methods. Trên một object `Dog`, methods được phân giải/gọi theo quy tắc Java và polymorphism.

Một class kế thừa **trực tiếp một class** (hoặc ngầm `Object`), có thể implement nhiều interfaces. Constructor chain tham gia khởi tạo object thuộc subclass. Trong body subclass, những private members của superclass **không tự trở thành accessible**.

### 1.1. Bốn nhóm dễ nhầm

| Nhóm | Ví dụ trong Parent | Điều cần nhớ ở Child |
| --- | --- | --- |
| Public/protected/package-visible member được thừa hưởng theo quy tắc | `public void run()` | Có thể dùng với điều kiện access phù hợp |
| Private member của Parent | `private int balance` | Không được kế thừa như accessible member của Child; vẫn thuộc state/behavior Parent |
| Member Child tự khai báo | `String label` | Thuộc Child; có thể có tên trùng member Parent |
| Constructor Parent | `Parent(int id)` | **Không được kế thừa**; Child constructor có thể gọi `super(id)` nếu accessible |

**Lưu ý:** Cụm “thành viên của class” trong JLS có định nghĩa chi tiết về declared/inherited members. Hãy dùng cách nói **“field private vẫn là state của phần superclass trong object nhưng không được subclass thừa hưởng để truy cập trực tiếp”** thay vì “private field bị xóa khi tạo subclass”.

## 2. Quy tắc thành viên được kế thừa

Trong các tình huống class thông dụng, lớp con có thể kế thừa những **non-private** fields, instance methods và nested member types đủ điều kiện theo quan hệ superclass/interfaces và **quy tắc accessibility**.

Không phải bất kỳ member nào xuất hiện trong Parent cũng trở thành một tên dùng trực tiếp hợp lệ ở Child. Cần xét:

1. Member thuộc **class/interface khai báo nào**?
2. Member có access modifier nào?
3. Child có thuộc **cùng package** không?
4. Child có **khai báo thành viên cùng tên/chữ ký** để hide/override không?
5. Member là **instance method**, **static method**, **field**, **nested type** hay **constructor**?
6. Nếu có nhiều supertypes/interfaces, có xung đột names/default methods không?

### 2.1. Bảng điều hướng access trong tình huống điển hình

| Khai báo trong Parent | Child cùng package | Child khác package | Code bất kỳ khác package |
| --- | --- | --- | --- |
| `public` | Truy cập được | Truy cập được | Truy cập được nếu owner type accessible |
| `protected` | Truy cập được trong package | Truy cập theo quy tắc subclass đặc biệt | Thường không truy cập được |
| Không modifier (*package-private*) | Truy cập được trong package | Không accessible qua tư cách subclass | Không |
| `private` | **Không** trực tiếp, dù cùng package | **Không** trực tiếp | Không |

Bảng là **mô hình lớp top-level public trong packages thông thường**. Khi áp dụng còn có các ngoại lệ/quy tắc về nested classes, nestmates, modules, access to type, protected qualified receivers và reflection. Những ngoại lệ ấy **không đổi nguyên tắc**: riêng subclass không được cấp quyền đọc private member của superclass.

### 2.2. Package-private không phải `protected`

Viết:

~~~java
class Parent {
    int packageValue = 1;
}
~~~

không có từ khóa access modifier nghĩa là **package-private**. Nó được truy cập trong cùng package theo quy tắc, nhưng **không tự mở cho subclasses ở package khác**.

Tên “default access” thường được dùng không chính thức cho package-private, nhưng không nên nhầm với **`default` keyword trong interface methods**. Hai ý nghĩa khác nhau.

## 3. Private field vẫn góp vào trạng thái của một object Child

Xét:

~~~java
class Account {
    private long balanceCents;
}

class SavingsAccount extends Account {
}
~~~

Một object `SavingsAccount` vẫn có phần trạng thái do `Account` định nghĩa. Private field `balanceCents` **không biến mất**, không phải có giá trị “undefined”, và không thể được subclass tự truy cập bằng `balanceCents` hay `super.balanceCents`.

Lớp cha có thể cung cấp các methods công khai hoặc được bảo vệ để quan sát/cập nhật có kiểm soát:

~~~java
class Account {
    private long balanceCents;

    public long balanceCents() {
        return balanceCents;
    }

    public void deposit(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        balanceCents = Math.addExact(balanceCents, amount);
    }
}

class SavingsAccount extends Account {
    public void addInterestBonus(long bonus) {
        deposit(bonus);
    }
}
~~~

Hai classes này là ví dụ minh họa hợp lệ trong cùng package. `SavingsAccount` gọi **public method `deposit`** được kế thừa/accessible, chứ không được tự viết `balanceCents += bonus` để phá invariant.

Thiết kế như vậy giữ trách nhiệm kiểm soát state ở **class sở hữu field**, không giao cho mọi subclass quyền ghi trực tiếp.

## 4. Chương trình đầu tiên: kế thừa API nhưng bảo vệ private state

Lưu **`PrivateStateInheritanceDemo.java`**:

~~~java
public class PrivateStateInheritanceDemo {
    static class Account {
        private long balance;

        Account(long openingBalance) {
            if (openingBalance < 0) {
                throw new IllegalArgumentException("negative opening");
            }
            balance = openingBalance;
        }

        public final long balance() {
            return balance;
        }

        public final void deposit(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("invalid deposit");
            }
            balance = Math.addExact(balance, amount);
        }

        protected final void withdraw(long amount) {
            if (amount <= 0 || amount > balance) {
                throw new IllegalArgumentException("invalid withdrawal");
            }
            balance -= amount;
        }
    }

    static final class SavingsAccount extends Account {
        SavingsAccount(long initialBalance) {
            super(initialBalance);
        }

        void useForPurchase(long amount) {
            withdraw(amount);
        }

        void creditReward(long amount) {
            deposit(amount);
        }
    }

    public static void main(String[] args) {
        SavingsAccount account = new SavingsAccount(1000);
        System.out.println("initial=" + account.balance());

        account.creditReward(250);
        account.useForPurchase(400);
        System.out.println("after=" + account.balance());

        try {
            account.useForPurchase(2000);
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid purchase rejected");
        }

        System.out.println("final=" + account.balance());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac PrivateStateInheritanceDemo.java
java PrivateStateInheritanceDemo
~~~

**Stdout:**

~~~text
initial=1000
after=850
invalid purchase rejected
final=850
~~~

Phân tích:

- `Account.balance` là private. Nó vẫn thuộc trạng thái của object `SavingsAccount`.
- Constructor subclass gọi `super(initialBalance)` để class cha thiết lập số dư hợp lệ.
- Subclass gọi `deposit` và `withdraw` có hợp đồng kiểm tra giá trị, không tự gán vào field private.
- `balance()`, `deposit`, `withdraw` là `final` methods trong ví dụ để subclasses không thể override các bước bảo vệ bất biến đã thiết kế.
- `withdraw` được khai báo `protected` nên Child thuộc một subclass có thể gọi nó ở ngữ cảnh phù hợp. Không có nghĩa mọi client khác package cũng có quyền gọi.
- Lần rút 2000 bị từ chối trước khi cập nhật, nên balance giữ 850.

### 4.1. Vì sao dùng `private` tốt hơn `protected long balance` trong nhiều trường hợp?

Nếu field là `protected`, subclass có thể làm:

~~~java
// balance = -900; // Nếu field protected và accessible, phép gán này
//                  // có thể bỏ qua validation của Account.
~~~

Một subclass sai làm hỏng invariant của Parent, khiến mọi method của Account phải đối phó state không hợp lệ.

Đóng gói state thành private cùng **protected methods có nghĩa nghiệp vụ** (như `withdraw`) giúp extension không cần đụng representation trực tiếp. `protected` phù hợp cho extension points đã được cân nhắc, không phải giải pháp mặc định để chia sẻ mọi fields.

## 5. `private` khác `final` và `static`

Các modifiers trả lời những câu hỏi khác nhau:

- `private`: **ai được phép truy cập member qua rules của ngôn ngữ**?
- `final` trên field: field có được **gán lại** sau initialization hợp lệ không?
- `final` trên method: method có được subclass **override** không?
- `static`: member gắn với **class** thay vì từng instance, cùng quy tắc tương ứng.
- `abstract`: class/method có nghĩa vụ cần implementation của subclass theo type hierarchy (theo các ràng buộc ngôn ngữ).

Ví dụ:

~~~java
class Base {
    private final String id = "A";
    protected final int version = 1;
    private static int privateCounter;
}
~~~

Các fields `id` và `privateCounter` không trở thành members truy cập trực tiếp từ subclasses chỉ vì `final` hoặc `static`. `version` được khai báo protected final và có thể được truy cập trong subclass theo rules; không thể gán lại nó từ code thông thường.

### 5.1. Final reference không làm object immutable

~~~java
class Base {
    private final java.util.ArrayList<String> items =
            new java.util.ArrayList<>();
}
~~~

`items` là một reference field final, nhưng object `ArrayList` được giữ vẫn mutable trong các methods có quyền. Private che field khỏi subclass, còn API getters/setters phải được thiết kế để tránh lộ reference mutable.

**Đừng dùng `protected` getter trả thẳng mutable internal list** nếu subclass có thể `clear()` và phá invariant.

## 6. Vì sao `super.privateField` không hợp lệ?

`super.field` không phải cơ chế “bỏ qua” access control. Nó giúp biểu thức chọn một field/member phù hợp từ superclass theo JLS, nhưng vẫn phải tuân **accessibility**.

Ví dụ cố ý sai:

~~~java
class Parent {
    private int secret = 5;
}

class Child extends Parent {
    void show() {
        // System.out.println(secret);       // Không accessible.
        // System.out.println(super.secret); // Cũng không accessible.
    }
}
~~~

Dù một Child object có phần Parent chứa `secret`, code ở Child không có quyền đọc field đó. Giải pháp là cung cấp API có ý nghĩa từ Parent:

~~~java
class Parent {
    private int secret = 5;

    protected int secretValue() {
        return secret;
    }
}

class Child extends Parent {
    int read() {
        return secretValue();
    }
}
~~~

Hai bộ class trên là **các phiên bản thay thế** minh họa. Không đặt cả hai khai báo `Parent` trong cùng package/file rồi biên dịch chung.

**Không nên** dùng reflection để mở private field chỉ nhằm né thiết kế API; ngoài nguy cơ phá invariants còn có module encapsulation, security và portability.

## 7. Method `private` không bị override

Đây là điểm rất quan trọng cho polymorphism.

Một **instance method private** của Parent **không được kế thừa** như một override target ở Child. Khi Child khai báo một method **cùng tên và parameter types**, đó có thể là **method mới**, không phải override của Parent.privateMethod.

### 7.1. Ví dụ độc lập

Lưu **`PrivateMethodDispatchDemo.java`**:

~~~java
public class PrivateMethodDispatchDemo {
    static class Parent {
        private String label() {
            return "Parent.private";
        }

        public String describeInsideParent() {
            return label();
        }
    }

    static class Child extends Parent {
        public String label() {
            return "Child.public";
        }
    }

    public static void main(String[] args) {
        Child child = new Child();

        System.out.println(child.describeInsideParent());
        System.out.println(child.label());

        Parent asParent = child;
        System.out.println(asParent.describeInsideParent());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac PrivateMethodDispatchDemo.java
java PrivateMethodDispatchDemo
~~~

Output:

~~~text
Parent.private
Child.public
Parent.private
~~~

**Vì sao vậy?**

- `Parent.describeInsideParent()` gọi `label()` **do Parent khai báo private**. Lời gọi đó không dispatch tới `Child.label()` như một overridden method.
- `Child.label()` là một method công khai mới có cùng tên và chữ ký, được khai báo ở Child.
- Tham chiếu kiểu `Parent` không có public `label()` để gọi trực tiếp. `asParent.describeInsideParent()` vẫn chạy method Parent gọi helper private của Parent.
- Thay `Child.label()` bằng method có annotation `@Override` trong tình huống này gây compile-time error: nó **không thực sự override method từ superclass**.

### 7.2. Vì sao private methods không thể là dynamic extension points?

Lớp cha có thể dùng private method để thực hiện chi tiết triển khai **không bị subclass thay thế**, bảo vệ logic nội bộ khỏi override ngẫu nhiên. Muốn subclass được customization, thiết kế một `protected`/**public** instance method có hợp đồng rõ và gọi nó ở thời điểm an toàn.

Đừng đổi method private thành protected chỉ để test dễ truy cập mà không cân nhắc ảnh hưởng tới inheritance contract và khả năng subclasses ghi đè.

## 8. Private method và annotation `@Override`

Một lỗi compiler dễ gặp:

~~~java
class Parent {
    private void perform() {
    }
}

class Child extends Parent {
    // @Override                 // Không hợp lệ trong tình huống này.
    void perform() {
    }
}
~~~

Dòng `@Override` được comment vì `Parent.perform()` private, không phải inherited override target.

Nếu sửa Parent method thành:

~~~java
protected void perform() {
}
~~~

và giữ Child method là package-private `void perform()` thì lại có **lỗi khác**: cannot reduce visibility của overridden method. Child override ít nhất phải `protected` (hoặc `public`) trong bối cảnh hợp lệ.

**Hai nhóm quy tắc độc lập:**

1. Có inherited, overrideable method target hợp lệ hay không?
2. Nếu có, override có đúng chữ ký, return type, access level, exceptions và các rules khác không?

Annotation `@Override` là một cách kiểm tra của compiler rất hữu ích để tránh tưởng mình override nhưng thực ra khai báo method mới.

## 9. So sánh với overriding thực sự: dynamic dispatch

Lưu **`InheritedMethodOverrideDemo.java`**:

~~~java
public class InheritedMethodOverrideDemo {
    static class Animal {
        private final String name;

        Animal(String name) {
            this.name = name;
        }

        public String name() {
            return name;
        }

        public String sound() {
            return "...";
        }

        public String introduction() {
            return name() + " says " + sound();
        }
    }

    static class Dog extends Animal {
        Dog(String name) {
            super(name);
        }

        @Override
        public String sound() {
            return "woof";
        }

        public String parentSound() {
            return super.sound();
        }
    }

    public static void main(String[] args) {
        Animal animal = new Dog("Milo");

        System.out.println(animal.introduction());
        System.out.println(animal.sound());
        System.out.println(((Dog) animal).parentSound());
    }
}
~~~

Lệnh:

~~~bash
javac InheritedMethodOverrideDemo.java
java InheritedMethodOverrideDemo
~~~

Output:

~~~text
Milo says woof
woof
...
~~~

**Giải thích:**

- `name` của Animal vẫn là private state. Dog không đọc trực tiếp field đó; `name()` là inherited public accessor.
- `sound()` là public instance method, được Dog override hợp lệ.
- Trong `animal.introduction()` (implementation khai báo trong Animal), lời gọi `sound()` có dynamic dispatch nên chạy `Dog.sound()` vì runtime object là Dog.
- `super.sound()` trong Dog gọi implementation superclass một cách tường minh (ở ngữ cảnh hợp lệ), trả `"..."`.
- Đây là sự khác biệt cốt lõi với **private method** trong ví dụ `PrivateMethodDispatchDemo`.

### 9.1. `super` không phải một object Animal tách biệt

`super.sound()` chọn implementation từ superclass, không tạo một Animal object khác. `Dog` object có cùng identity dù code chạy method Animal hay Dog.

Tương tự, private field của Animal là state của phần superclass trong Dog object, không phải một field nằm trong một object Animal riêng được cấp phát bởi `super(...)`.

## 10. Constructors không được kế thừa

Trong Java, constructors không phải methods được kế thừa. Một class Child **không tự có** những constructor cùng chữ ký với Parent.

Nếu:

~~~java
class Parent {
    Parent(int value) {
    }
}

class Child extends Parent {
}
~~~

đây là **ví dụ cố ý sai**: compiler muốn tạo default constructor `Child()` gọi implicit `super()`, nhưng Parent không có accessible constructor không tham số. Child cũng không tự có constructor `Child(int)` vì Parent có `Parent(int)`.

Sửa bằng cách khai báo constructor subclass rõ:

~~~java
class Parent {
    Parent(int value) {
    }
}

class Child extends Parent {
    Child(int value) {
        super(value);
    }
}
~~~

Hai blocks thay thế nhau, không biên dịch đồng thời vì trùng names.

### 10.1. Private constructor của superclass

Một subclass bên ngoài class Parent không được gọi một constructor `private Parent(...)` thông thường bằng `super(...)`. Điều này có thể được dùng để kiểm soát việc tạo instances hoặc ngăn các dạng kế thừa không chủ ý.

Ví dụ:

~~~java
class Parent {
    private Parent() {
    }
}

class Child extends Parent {
    // Child() { super(); } // Không hợp lệ: Parent() inaccessible.
}
~~~

Đây là **ví dụ lỗi compile-time**, bởi kể cả khi bỏ Child constructor tường minh, implicit default constructor của Child vẫn cần gọi `super()` inaccessible.

Nếu thiết kế Parent cho phép subclasses, cân nhắc `protected Parent(...)` theo contract. Không có access modifier nào khiến constructor trở thành “inherited constructor”.

## 11. Chương trình constructor và private state

Lưu **`PrivateConstructorStateDemo.java`**:

~~~java
public class PrivateConstructorStateDemo {
    static class Person {
        private final String name;
        private final int age;

        protected Person(String name, int age) {
            if (name == null || name.isBlank() || age < 0) {
                throw new IllegalArgumentException("invalid person");
            }
            this.name = name;
            this.age = age;
        }

        public final String summary() {
            return name + "(" + age + ")";
        }
    }

    static final class Student extends Person {
        private final String className;

        Student(String name, int age, String className) {
            super(name, age);
            this.className = className;
        }

        String describe() {
            return summary() + ",class=" + className;
        }
    }

    public static void main(String[] args) {
        Student student = new Student("Lan", 17, "12A");
        System.out.println(student.describe());
        System.out.println(student.summary());

        try {
            new Student("Minh", -1, "12B");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid parent state rejected");
        }
    }
}
~~~

Chạy:

~~~bash
javac PrivateConstructorStateDemo.java
java PrivateConstructorStateDemo
~~~

Output:

~~~text
Lan(17),class=12A
Lan(17)
invalid parent state rejected
~~~

`Person` dùng private final fields và protected constructor. Khi tạo Student, superclass tự validate phần state mà nó sở hữu. Student không truy cập trực tiếp `name`/`age` mà dùng public final `summary()`.

Điểm cần nhớ: **private constructor khác private field**, nhưng cùng chịu access control. Muốn subclass có thể khởi tạo superclass thì Parent phải cung cấp **accessible constructor path**.

## 12. Package-private: cùng package khác với khác package

Java package là một phần quan trọng của access control.

- Một class và subclass **trong cùng package** có thể dùng package-private members của class cha theo quy tắc inheritance/accessibility.
- Một subclass **ở package khác** không thể dựa vào `extends` để truy cập package-private fields/methods của Parent.
- Dùng `public` hoặc `protected` có chủ đích nếu một phần API cần cho code bên ngoài package, nhưng không vì tiện mà mở toàn bộ state.

### 12.1. Ví dụ chạy được trong cùng package/file

Lưu **`PackageVisibilityDemo.java`**:

~~~java
public class PackageVisibilityDemo {
    static class Parent {
        int packageValue = 7;
        private int secret = 100;

        int packageMethod() {
            return packageValue + secret;
        }
    }

    static class Child extends Parent {
        int inspect() {
            return packageValue;
        }

        int useMethod() {
            return packageMethod();
        }
    }

    public static void main(String[] args) {
        Child child = new Child();

        System.out.println("package field=" + child.inspect());
        System.out.println("package method=" + child.useMethod());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac PackageVisibilityDemo.java
java PackageVisibilityDemo
~~~

Output:

~~~text
package field=7
package method=107
~~~

Các nested classes `Parent` và `Child` cùng nằm trong một top-level class nên cũng cùng package. `packageValue` và `packageMethod` là package-private. `secret` private được **method của Parent** dùng để tính 107; Child không tự đọc field `secret`.

### 12.2. Cross-package làm khác hành vi compile-time

Một subclass ở package khác **không có quyền** trực tiếp đọc package-private `packageValue` từ Parent. Nó có thể gọi `public` method do Parent cung cấp, hoặc dùng `protected` member khi thỏa điều kiện subclass/receiver phù hợp.

Đừng đánh đồng package-private với Java module visibility. Modules có thêm quy tắc readability/exports, nhưng `private` và `protected` vẫn có ngữ nghĩa ngôn ngữ riêng.

## 13. Ví dụ hai packages và `protected`

Tạo cấu trúc thư mục:

~~~text
project/
  api/
    Base.java
  client/
    Child.java
    Main.java
~~~

Nội dung **`api/Base.java`**:

~~~java
package api;

public class Base {
    int packageValue = 7;
    protected int protectedValue = 8;
    public int publicValue = 9;
    private int secret = 10;

    protected String format() {
        return "Base-format";
    }

    public int secretValue() {
        return secret;
    }
}
~~~

Nội dung **`client/Child.java`**:

~~~java
package client;

import api.Base;

public class Child extends Base {
    public String inspect() {
        return protectedValue + "," + publicValue
                + "," + secretValue();
    }

    public String callProtected() {
        return format();
    }

    public int inspectOtherChild(Child other) {
        return other.protectedValue;
    }
}
~~~

Nội dung **`client/Main.java`**:

~~~java
package client;

public class Main {
    public static void main(String[] args) {
        Child first = new Child();
        Child second = new Child();

        System.out.println("values=" + first.inspect());
        System.out.println("format=" + first.callProtected());
        System.out.println("other=" + first.inspectOtherChild(second));
    }
}
~~~

Biên dịch từ thư mục `project`:

~~~bash
javac -d out api/Base.java client/Child.java client/Main.java
java -cp out client.Main
~~~

Output:

~~~text
values=8,9,10
format=Base-format
other=8
~~~

**Giải thích:**

1. `Child` ở package `client`, `Base` ở package `api`.
2. `protectedValue` và `format()` protected nên Child có thể dùng trong code subclass theo quy tắc.
3. `publicValue` và `secretValue()` public, accessible vì Base public trong package được dùng.
4. `packageValue` không accessible từ Child; nó là package-private trong package `api`.
5. `secret` private không được Child đọc trực tiếp. Giá trị 10 đi qua `Base.secretValue()`.
6. `other.protectedValue` hợp lệ trong body của Child vì qualifier `other` có kiểu tĩnh `Child`; phần tiếp theo giải thích giới hạn receiver quan trọng.

### 13.1. Bẫy protected ở package khác: `Base other`

Ở trong Child thuộc package `client`, điều này có thể hợp lệ:

~~~java
int a = this.protectedValue;
int b = otherChild.protectedValue; // otherChild có kiểu Child.
~~~

Nhưng đoạn sau có thể bị từ chối:

~~~java
void inspectBase(api.Base otherBase) {
    // int x = otherBase.protectedValue; // Không hợp lệ tại đây.
}
~~~

Trong Java, access protected từ subclass **ngoài package khai báo** có thêm giới hạn về **kiểu tĩnh của expression qualifier** khi truy cập instance field/method. Không phải cứ “đang ở một subclass” là được truy cập protected member thông qua **bất kỳ object Base nào**.

Điều này bảo vệ một subclass khỏi việc tùy ý dùng đặc quyền protected để truy cập state của một Base object không thuộc đúng loại receiver được cho phép.

### 13.2. Cùng package có khác không?

Có. Code ở **cùng package `api`** với Base có thể truy cập protected member của Base theo package-accessibility ngay cả khi không phải subclass, nếu các rules khác cho phép.

Bởi vậy khi chuyển một class sang package khác, đôi khi access tới `protected` bắt đầu báo lỗi dù chữ `protected` không thay đổi.

## 14. Private fields không thể override; cùng tên chỉ là field hiding

Khái niệm **overriding** áp dụng cho instance methods đủ điều kiện, không cho fields. Fields có thể bị **hide** bởi declarations cùng tên trong subclass.

### 14.1. Ví dụ field cùng tên trong superclass/subclass

Lưu **`FieldHidingDemo.java`**:

~~~java
public class FieldHidingDemo {
    static class Parent {
        public int value = 10;

        public int parentValue() {
            return value;
        }
    }

    static class Child extends Parent {
        public int value = 20;

        public int childValue() {
            return value;
        }
    }

    public static void main(String[] args) {
        Child child = new Child();
        Parent parentView = child;

        System.out.println("parent view=" + parentView.value);
        System.out.println("child view=" + child.value);
        System.out.println("parent method=" + child.parentValue());
        System.out.println("child method=" + child.childValue());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac FieldHidingDemo.java
java FieldHidingDemo
~~~

Output:

~~~text
parent view=10
child view=20
parent method=10
child method=20
~~~

**Tại sao?**

- `Parent.value` và `Child.value` là **hai field declarations**, dù cùng tên.
- `parentView.value` chọn field theo kiểu tĩnh `Parent`, không dynamic dispatch như method override.
- `child.value` chọn field của Child.
- `parentValue()` thực thi trong Parent, nên tên `value` tham chiếu Parent.value; `childValue()` trong Child tham chiếu Child.value.
- Cả hai fields có thể cùng tồn tại trong **một Child object**.

### 14.2. Private field cùng tên không phải override

Nếu Parent khai báo `private int value` và Child khai báo `int value`, hai fields vẫn là hai thành phần state khác nhau. Child không thể viết `super.value` để đọc private field Parent. Tên cùng nhau **không đổi** quyền truy cập hay biến state của Parent thành state của Child.

**Khuyến nghị:** tránh field hiding trừ khi có lý do rõ; nó khiến code dễ nhầm giữa việc truy cập theo kiểu tĩnh và polymorphic dispatch của methods.

## 15. Chương trình hai private fields trùng tên

Lưu **`DistinctPrivateFieldsDemo.java`**:

~~~java
public class DistinctPrivateFieldsDemo {
    static class Parent {
        private int value = 10;

        public int parentValue() {
            return value;
        }

        public void incrementParent() {
            value++;
        }
    }

    static class Child extends Parent {
        private int value = 100;

        public int childValue() {
            return value;
        }

        public void incrementChild() {
            value++;
        }
    }

    public static void main(String[] args) {
        Child child = new Child();

        System.out.println("initial parent=" + child.parentValue());
        System.out.println("initial child=" + child.childValue());

        child.incrementParent();
        child.incrementChild();

        System.out.println("after parent=" + child.parentValue());
        System.out.println("after child=" + child.childValue());
    }
}
~~~

Chạy:

~~~bash
javac DistinctPrivateFieldsDemo.java
java DistinctPrivateFieldsDemo
~~~

Output:

~~~text
initial parent=10
initial child=100
after parent=11
after child=101
~~~

Parent private `value` và Child private `value` là hai fields độc lập. `incrementParent()` sửa field Parent; `incrementChild()` sửa field Child. Mã này không dùng một field duy nhất được override.

Về mặt thiết kế, việc đặt trùng tên có thể khiến debugging khó hơn. Chỉ nên làm khi hai class thật sự có nghĩa state riêng và tên trùng không gây hiểu nhầm; thông thường nên chọn names diễn đạt rõ responsibility.

## 16. Static methods: hiding khác overriding

Một `static` method được gọi theo các quy tắc static method lookup/hiding, **không** polymorphic dynamic dispatch như instance method override.

Lưu **`StaticMethodHidingDemo.java`**:

~~~java
public class StaticMethodHidingDemo {
    static class Parent {
        static String label() {
            return "Parent.static";
        }

        public String describe() {
            return label();
        }
    }

    static class Child extends Parent {
        static String label() {
            return "Child.static";
        }
    }

    public static void main(String[] args) {
        Parent p = new Child();
        Child c = new Child();

        System.out.println("via Parent=" + p.label());
        System.out.println("via Child=" + c.label());
        System.out.println("inherited describe=" + c.describe());
    }
}
~~~

Chạy:

~~~bash
javac StaticMethodHidingDemo.java
java StaticMethodHidingDemo
~~~

Output:

~~~text
via Parent=Parent.static
via Child=Child.static
inherited describe=Parent.static
~~~

**Giải thích:**

- `Parent.label` và `Child.label` là static methods cùng chữ ký. Child method **hides** Parent method trong những điều kiện phù hợp, không override.
- `p.label()` qua expression kiểu tĩnh Parent liên kết tới Parent static method.
- `c.label()` qua expression kiểu tĩnh Child chọn Child static method.
- `Parent.describe()` gọi `label()` từ ngữ cảnh Parent, không dynamic dispatch tới Child static method.
- Java cho phép dùng expression để truy cập static method trong một số ngữ cảnh nhưng **nên viết `Parent.label()`/`Child.label()`** cho rõ rằng method thuộc class, không instance.

Private static method của Parent **không được Child kế thừa**; Child có thể khai báo static method trùng tên mà không tạo hiding relationship theo nghĩa inherited member đó.

## 17. Không thể giảm quyền truy cập khi override

Nếu Parent định nghĩa:

~~~java
public void process() {
}
~~~

thì Child override hợp lệ phải tiếp tục public:

~~~java
@Override
public void process() {
}
~~~

Không thể viết `protected void process()` hay package-private `void process()` khi override public method Parent, vì như vậy làm giảm accessibility của phương thức trong subtype.

Nếu Parent method là `protected`, Child có thể override thành `protected` hoặc `public`, nhưng không thể chuyển thành `private` trong một override hợp lệ.

### 17.1. Phân biệt “không override được” với “không truy cập được”

- `private Parent.method()`: subclass không kế thừa method đó như override target.
- `final Parent.method()` accessible: có thể inherited/called, nhưng subclass **không được override**.
- `static Parent.method()`: không phải instance override target; có thể bị hidden bởi static method phù hợp.
- Package-private Parent.method() ở package khác: không accessible/inherited theo các quy tắc áp dụng; không được giả định một method trùng tên ở Child sẽ là override của method ấy.
- `abstract` instance method accessible yêu cầu implementation ở concrete subclass, trừ khi đã được một lớp trung gian triển khai.

Các trường hợp có compile-time rules khác nhau. Khi compiler nói “attempting to assign weaker access privileges”, lỗi chỉ xuất hiện **sau khi có một override relationship phù hợp**.

## 18. `final` method và private helper: hai cách giữ hợp đồng lớp cha

Lớp cha có thể kiểm soát invariants theo hai mẫu:

**Mẫu A — private implementation:**

~~~java
class Parent {
    private void validateInternal() {
    }

    public void operation() {
        validateInternal();
    }
}
~~~

`validateInternal` là chi tiết nội bộ không bị subclasses override.

**Mẫu B — public final operation, protected hook:**

~~~java
abstract class Parent {
    public final void operation() {
        validate();
        performCore();
    }

    private void validate() {
        // Checks owned by Parent.
    }

    protected abstract void performCore();
}
~~~

Đây là skeleton minh họa. Template method `operation()` final khiến subclasses không override toàn bộ quy trình, còn `performCore()` là extension point được đặt chủ đích. Nhưng nếu gọi overridable/protected hook trong **constructor** trước khi subclass initialization hoàn tất, vẫn có rủi ro về incomplete state.

**Không đưa `protected` getter trả mutable representation chỉ để mở rộng**, trừ khi ownership và invariants đã được kiểm soát.

## 19. Constructors superclass có thể gọi overridden methods quá sớm

Kế thừa và đa hình còn có bẫy thời điểm khởi tạo. Object runtime type đã là Child khi code Parent constructor đang chạy. Nếu Parent constructor gọi một public/protected overridable method, lời gọi có thể dispatch đến Child implementation **trước khi field initializers của Child chạy**.

Lưu **`ConstructorOverrideRiskDemo.java`**:

~~~java
public class ConstructorOverrideRiskDemo {
    static class Parent {
        Parent() {
            System.out.println("parent begins");
            show();
        }

        protected void show() {
            System.out.println("Parent.show");
        }
    }

    static class Child extends Parent {
        private String label = "READY";

        Child() {
            System.out.println("child constructor");
        }

        @Override
        protected void show() {
            System.out.println("Child.show label=" + label);
        }
    }

    public static void main(String[] args) {
        Child child = new Child();
        child.show();
    }
}
~~~

Chạy:

~~~bash
javac ConstructorOverrideRiskDemo.java
java ConstructorOverrideRiskDemo
~~~

Output:

~~~text
parent begins
Child.show label=null
child constructor
Child.show label=READY
~~~

Private helper methods trong Parent không bị Child override, nên nếu Parent constructor **chỉ** dùng private/final logic dựa trên Parent state đã an toàn, dạng nguy cơ dispatch tới Child này được giảm. Tuy nhiên, **không phải mọi lần gọi private method từ constructor luôn an toàn**: helper vẫn có thể có I/O, publish `this`, đọc những state chưa initialized hoặc tạo side effects khác.

**Nguyên tắc:** constructor superclass không nên phụ thuộc behavior của subclass chưa hoàn tất khởi tạo. Dành callback/extension hook cho giai đoạn sau khi object được xây dựng đầy đủ.

## 20. Member nested types và inheritance

Ngoài fields và methods, Java có **member types** (như static nested class, non-static inner class và member interfaces theo quy tắc). Một nested type được khai báo với accessibility phù hợp cũng có thể được dùng qua inheritance/name lookup phù hợp.

Ví dụ:

~~~java
class Parent {
    public static class Token {
        public final int id;

        public Token(int id) {
            this.id = id;
        }
    }
}

class Child extends Parent {
}
~~~

Code có thể viết `Child.Token` để tham chiếu member type `Token` được thừa hưởng/tra cứu từ Parent khi hợp lệ.

### 20.1. Chương trình runnable

Lưu **`InheritedMemberTypeDemo.java`**:

~~~java
public class InheritedMemberTypeDemo {
    static class Parent {
        public static class Token {
            private final int id;

            public Token(int id) {
                this.id = id;
            }

            public int id() {
                return id;
            }
        }
    }

    static class Child extends Parent {
        public String useToken() {
            Token token = new Token(7);
            return "token=" + token.id();
        }
    }

    public static void main(String[] args) {
        Child child = new Child();
        Child.Token token = new Child.Token(9);

        System.out.println(child.useToken());
        System.out.println("external=" + token.id());
    }
}
~~~

Chạy:

~~~bash
javac InheritedMemberTypeDemo.java
java InheritedMemberTypeDemo
~~~

Output:

~~~text
token=7
external=9
~~~

`Token` được khai báo bởi Parent, public static nested type. Trong ví dụ, Child có thể dùng tên `Token` và `Child.Token` được phân giải phù hợp. Một member type khai báo `private` trong Parent **không** trở thành một type accessible trực tiếp từ subclass; vẫn phải tuân access control.

### 20.2. Nested và inner class có những điểm riêng

Một **non-static inner class** gắn với một enclosing instance. Một **static nested class** không mang enclosing instance theo cùng cách. Inheritance của nested *type name* không phải inheritance của constructor, cũng không có nghĩa tạo `new Child.Token()` sẽ khởi tạo một Child object.

Tránh nhầm các cấp:

- Inheritance giữa Parent và Child.
- Lexical nesting của class Token bên trong Parent.
- Quan hệ giữa instance của inner class và enclosing instance.

## 21. Members từ interface: default method, private helper và static method

Java interfaces có thể khai báo:

- Public abstract methods (theo ngữ nghĩa interface).
- **Default instance methods** có implementation.
- **Static methods** thuộc chính interface.
- **Private methods** (từ Java 9) giúp tái sử dụng implementation nội bộ trong interface.
- Fields của interface, ngầm `public static final`.

Một class implements interface có thể kế thừa/triển khai các **public abstract/default instance methods** theo interface inheritance rules và conflict resolution. Nhưng **private interface helper không được class implementer kế thừa** như callable method; **static interface method cũng không được gọi như inherited static member trên implementer**.

### 21.1. Chương trình interface với private helper

Lưu **`InterfaceMemberVisibilityDemo.java`**:

~~~java
public class InterfaceMemberVisibilityDemo {
    interface Greeter {
        default String greet(String name) {
            return decorate(name);
        }

        private String decorate(String text) {
            return "Hello " + text;
        }

        static String category() {
            return "greeting";
        }
    }

    static final class FriendlyGreeter implements Greeter {
    }

    public static void main(String[] args) {
        FriendlyGreeter greeter = new FriendlyGreeter();

        System.out.println(greeter.greet("Lan"));
        System.out.println(Greeter.category());
    }
}
~~~

Chạy:

~~~bash
javac InterfaceMemberVisibilityDemo.java
java InterfaceMemberVisibilityDemo
~~~

Output:

~~~text
Hello Lan
greeting
~~~

**Giải thích:**

- `FriendlyGreeter` được dùng như một implementation của Greeter; `greet` có default implementation và được gọi qua object.
- `Greeter.greet` có thể gọi private helper `decorate` vì nó nằm trong chính interface.
- `FriendlyGreeter` **không có quyền gọi `decorate` như inherited method**.
- Static method `category` phải được gọi theo tên khai báo của interface `Greeter.category()`, không phải `FriendlyGreeter.category()`.
- Một private interface method không là extension hook cho implementers. Nếu cần method mà implementer phải cung cấp, khai báo abstract public interface method phù hợp.

### 21.2. Interface field không phải instance field

Nếu interface định nghĩa `int LIMIT = 10;`, đó là `public static final` field theo quy tắc, không phải một field riêng của mỗi implementation object. Class implementer không thể thay giá trị bằng cách “override field”; fields không được override.

Có thể phát sinh trùng tên constant giữa nhiều interfaces. Khi names bị ambiguous, dùng qualification `InterfaceName.CONSTANT` để chỉ rõ. Trong API thực, tránh dùng implements interface chỉ để “mượn constants”, vì đưa implementation details vào type hierarchy không cần thiết.

## 22. Một subclass có thể gọi private member gián tiếp

Không phải mọi việc cần private field đều đòi đổi field thành `protected`. Parent có thể **cung cấp hành vi**:

~~~java
class Account {
    private long balance;

    public long balance() {
        return balance;
    }

    protected void debit(long amount) {
        if (amount <= 0 || amount > balance) {
            throw new IllegalArgumentException("invalid debit");
        }
        balance -= amount;
    }
}
~~~

Subclass gọi `debit(amount)` để thực hiện nghiệp vụ, và Parent vẫn quyết định giới hạn. Không lộ phương thức `setBalance(long arbitraryValue)` cho phép phá invariant.

### 22.1. Query vs command

- **Query** trả thông tin có ý nghĩa: `balance()`, `isActive()`, `canWithdraw(amount)`.
- **Command** thay state theo quy tắc: `withdraw(amount)`, `activate()`, `close()`.
- **Raw setter** như `setBalance(-1000)` là rủi ro nếu tồn tại chỉ để hỗ trợ subclass.

Khi logic trong Parent thay đổi (giới hạn số dư, kiểm toán, xác thực), subclasses dùng command API vẫn hưởng behavior đúng mà không sửa representation.

### 22.2. Bảo vệ mutable returned objects

Nếu Parent giữ `private List<Transaction> history` nhưng method `protected List<Transaction> history()` trả trực tiếp mutable list, Child vẫn có thể `clear()` làm sai state.

`private` field **không đủ** nếu Parent lộ reference mutable qua accessor. Cần immutable entries, `List.copyOf` snapshot, phương thức thêm event có validation hoặc ownership contract phù hợp.

## 23. Lớp cha abstract: private state và protected extension points

Một abstract class có thể đặt common private state và yêu cầu subclass triển khai behavior:

~~~java
abstract class Shape {
    private final String color;

    protected Shape(String color) {
        this.color = color;
    }

    public final String color() {
        return color;
    }

    public abstract double area();
}
~~~

Concrete subclass dùng `super(color)` để Parent khởi tạo color và override `area()` theo quy tắc. Không cần trao quyền gán lại field private color.

### 23.1. Chương trình hoàn chỉnh

Lưu **`AbstractPrivateStateDemo.java`**:

~~~java
public class AbstractPrivateStateDemo {
    static abstract class Shape {
        private final String color;

        protected Shape(String color) {
            this.color = color;
        }

        public final String color() {
            return color;
        }

        public abstract int area();
    }

    static final class Rectangle extends Shape {
        private final int width;
        private final int height;

        Rectangle(String color, int width, int height) {
            super(color);
            this.width = width;
            this.height = height;
        }

        @Override
        public int area() {
            return Math.multiplyExact(width, height);
        }
    }

    public static void main(String[] args) {
        Shape shape = new Rectangle("red", 3, 4);

        System.out.println("color=" + shape.color());
        System.out.println("area=" + shape.area());
    }
}
~~~

Chạy:

~~~bash
javac AbstractPrivateStateDemo.java
java AbstractPrivateStateDemo
~~~

Output:

~~~text
color=red
area=12
~~~

Ở đây field `color` là private final trong Shape nhưng tồn tại trong state object Rectangle. Interface công khai của Shape chỉ cho đọc color qua `color()`; behavior `area()` được Rectangle override. Đây là ví dụ tách rõ **state encapsulation** và **polymorphic extension**.

## 24. Quy tắc `protected` nên được dùng có chủ đích

Protected không đơn thuần có nghĩa “mọi class kế thừa đều đọc được mọi protected field trên bất kỳ object Parent nào”. Như phần cross-package, quyền truy cập có thể phụ thuộc receiver.

Khi thiết kế reusable library:

1. Dùng `private` cho representation details và helper methods không dành cho subclasses.
2. Chỉ cung cấp `protected` methods cho các extension points bạn thực sự muốn hỗ trợ lâu dài.
3. Ưu tiên methods có hợp đồng hơn protected mutable fields.
4. Cân nhắc `protected` constructors nếu chủ đích cho subclassing nhưng không muốn client tạo Parent trực tiếp.
5. Dùng `public final` methods cho phần logic bất biến quan trọng mà subclasses không được thay.
6. Kiểm thử một subclass **ở package khác** để phát hiện access assumptions sai.
7. Nếu Parent không thiết kế cho inheritance, cân nhắc `final class` hoặc factory/composition thay vì đưa ra subclass extension điểm mơ hồ.

### 24.1. Compatibility khi đổi access

Đổi một method từ `protected` sang `private` có thể làm subclasses đã biên dịch/mã nguồn mới gặp vấn đề, vì API inheritance contract thay đổi. Tương tự, đổi một instance method thành static hoặc làm nó final có thể ảnh hưởng overriding/linking.

Không xem access modifiers là lựa chọn chỉ để “compile cho qua”; chúng là phần quan trọng của **public/protected API contract**.

## 25. Chuyện reflection, nested classes và private access

**“Private inaccessible từ subclass”** không có nghĩa rằng không một cơ chế Java nào có thể đọc thông tin đó trong mọi tình huống. Java có quy tắc access riêng cho:

- Code bên trong chính class khai báo member.
- Nestmates/nested classes theo Java access control.
- Reflection theo quyền truy cập/module openness, nếu được phép.
- Serialization frameworks/instrumentation có quyền thực thi thích hợp.

Các cơ chế này **không làm field private trở thành inherited accessible field** cho một subclass bình thường.

### 25.1. Nested classes có thể truy cập private của enclosing class

Một nested class nằm trong cùng nest có thể truy cập private members theo quy tắc Java. Điều đó khác với một subclass nằm ở class top-level riêng.

Ví dụ:

~~~java
class Outer {
    private int secret = 9;

    class Inner {
        int read() {
            return secret;
        }
    }
}
~~~

`Inner` không truy cập secret vì nó extends Outer; nó là nested class có access privileges theo Java nesting rules. Đừng dùng trường hợp này để suy ra “Child extends Parent thì đọc private Parent được”.

### 25.2. Reflection không phải một kế hoạch kế thừa

API reflection có thể liệt kê declared fields kể cả private tùy API và cho phép inspection trong những phạm vi hợp lệ; thử `setAccessible(true)` có thể bị từ chối bởi module encapsulation hoặc các giới hạn khác. Việc một tool debugger/profiler hiển thị private field không có nghĩa source code subclass được gọi field ấy trực tiếp.

**Không dùng reflection để phá invariants** khi một protected/public method rõ nghĩa có thể giải quyết bài toán.

## 26. Polymorphism không “mở khóa” private members

Với:

~~~java
Parent ref = new Child();
~~~

dynamic dispatch có thể chọn implementation overridden instance method của Child, nhưng:

- Kiểu tĩnh `Parent` quyết định những members nào có thể gọi theo compile-time rules.
- Runtime type `Child` quyết định implementation của overridden instance method hợp lệ.
- Private members Parent không vì runtime object là Child mà tự truy cập được từ Child.
- Field access không dispatch như instance method overriding.
- Static methods không polymorphic như instance methods.
- Constructors không kế thừa/không override.

Do đó **access control, member inheritance, static type lookup và dynamic dispatch là bốn lớp quy tắc khác nhau**. Một chương trình đúng cần qua compile-time name/type/access checks trước khi nói tới method dispatch runtime.

## 27. Sai lầm phổ biến

| Sai lầm | Kết luận đúng |
| --- | --- |
| “Child được kế thừa tất cả fields của Parent kể cả private để dùng trực tiếp.” | Private Parent field không là accessible inherited field trong Child. |
| “Vì private không được kế thừa nên field đó không tồn tại trong Child object.” | Superclass state vẫn tồn tại và được Parent methods quản lý. |
| “`super.privateField` bỏ qua private.” | `super` không vượt access control. |
| “`private` giống package-private.” | Private chặt hơn; cùng package vẫn không tự được truy cập private. |
| “Package-private method của Parent luôn accessible ở subclass khác package.” | Không. `extends` không tự mở package boundary. |
| “Protected nghĩa là mọi subclass có thể đọc protected field của mọi Parent instance.” | Cross-package receiver restrictions vẫn áp dụng. |
| “Protected field luôn là extension API tốt.” | Lộ mutable representation dễ phá invariants; ưu tiên protected methods rõ nghĩa. |
| “Method Child trùng tên private Parent là override.” | Không; là method mới trong điều kiện phù hợp. |
| “`@Override` dùng được với private method Parent.” | Compiler phải báo lỗi nếu không có target thực sự override. |
| “Static method cùng tên là dynamic override.” | Static method hiding, không dynamic dispatch. |
| “Fields được override theo runtime object.” | Fields được resolve theo quy tắc compile-time/static type; field hiding khác overriding. |
| “`final` field làm object được reference trở nên immutable.” | Final ngăn gán lại field reference, không deep immutable. |
| “`final` method không thể inherited.” | Method final có thể inherited/called; chỉ không thể overridden. |
| “Constructors của Parent được kế thừa.” | Child phải có constructor riêng/default constructor và gọi super path hợp lệ. |
| “Private Parent constructor cho phép mọi subclass gọi `super()`.” | Không; constructor phải accessible. |
| “Private method Parent có thể bị polymorphic dispatch sang Child.” | Private method không override target; Parent gọi helper riêng. |
| “Subclass có thể override public method bằng protected.” | Không được giảm accessibility trong override. |
| “Class implement interface thừa hưởng private helper.” | Private interface method chỉ dành nội bộ interface. |
| “Static interface method gọi qua implementation class.” | Dùng `InterfaceName.staticMethod()`. |
| “Nested class được truy cập private chứng minh subclass nào cũng làm được.” | Nestmate/nesting privileges khác inheritance. |
| “Reflection nhìn thấy private tức là compiler cho phép Child đọc.” | Reflection/debug visibility không đổi source-level access. |
| “Override trong constructor Parent lúc nào cũng an toàn.” | Child field có thể còn 0/null; tránh overridable callbacks từ constructor. |
| “Một Child object là hai objects Parent và Child ghép lại.” | Đây là cùng một object có superclass/subclass initialization chain. |
| “Muốn dùng field thì cứ đổi `private` thành `public`.” | Cần thiết kế behavior-based API, không phá encapsulation. |

## 28. Checklist khi gặp lỗi kế thừa/access

Khi compiler báo “has private access”, “cannot find symbol”, “attempting to assign weaker access privileges” hoặc “method does not override”, kiểm tra:

1. **Superclass và subclass là ai?** Có đúng `extends`/`implements`?
2. **Member được khai báo ở đâu?** Parent, interface, outer/nested type hay Child?
3. **Member thuộc loại gì?** Field, constructor, instance/static method, nested type?
4. **Access modifier gì?** `private`, package-private, `protected`, `public`?
5. **Package của Parent/Child?** Có cùng package name thật không?
6. **Member non-private có thực sự inherited/accessibility phù hợp không?**
7. **Tên có bị hide hay override bởi member Child không?**
8. **Method có `static` hoặc `final` không?** Có cho override không?
9. **Nếu override, có đổi return type/access/checked exceptions sai không?**
10. **Nếu protected ngoài package, receiver có kiểu tĩnh phù hợp không?**
11. **Constructor Child gọi `super(...)` hợp lệ không?** Parent constructor accessible không?
12. **Tham chiếu biểu thức có static type gì?** Runtime type chỉ ảnh hưởng dispatch khi phù hợp.
13. **API cha đã có query/command thay direct field access chưa?**
14. **Dùng `@Override` để compiler xác nhận override relationship chưa?**
15. **Thay vì thừa kế, composition có phản ánh quan hệ nghiệp vụ tốt hơn không?**

Chẩn đoán đúng nhóm quy tắc sẽ giúp sửa từ thiết kế: mở đúng API, đổi signature/visibility, chuyển responsibility về owner class, hay dùng `super(...)` hợp lệ — không phải tùy tiện chuyển mọi member sang public.

## 29. Bài tập tự kiểm tra có đáp án

**Câu 1.** Parent có `private int id`, Child extends Parent. Child đọc `id` trực tiếp có được không?  
**Đáp án:** Không. Field private của Parent không là inherited accessible member trong Child.

**Câu 2.** Nếu Child không đọc `id` trực tiếp, object Child có phần state `id` của Parent không?  
**Đáp án:** Có. Parent constructor/methods vẫn có thể quản lý field trong phần superclass state.

**Câu 3.** `super.id` có bỏ qua private không?  
**Đáp án:** Không. `super` không phá access-control rules.

**Câu 4.** Parent có `public int id()` trả private field. Child có thể gọi `id()` không?  
**Đáp án:** Có nếu method accessible/inherited theo quy tắc; đây là API Parent cung cấp.

**Câu 5.** Parent có `private void f()`, Child khai báo `public void f()`. Có override không?  
**Đáp án:** Không. Child method là khai báo mới; private Parent method không bị override.

**Câu 6.** Đặt `@Override` lên `Child.f()` trong câu 5 có được không?  
**Đáp án:** Không, compiler sẽ báo method does not override theo tình huống đã mô tả.

**Câu 7.** Khi Parent method gọi `private f()`, runtime object là Child có `public f()` mới. Method nào chạy?  
**Đáp án:** Parent.private f(), không dynamic dispatch sang Child f().

**Câu 8.** Nếu Parent khai báo `public void f()` và Child override hợp lệ, reference kiểu Parent trỏ Child gọi f() chạy gì?  
**Đáp án:** Child implementation do dynamic dispatch của overridden instance method.

**Câu 9.** `final public void f()` của Parent có được Child gọi không?  
**Đáp án:** Có thể kế thừa/gọi nếu accessible, nhưng Child không được override.

**Câu 10.** Parent khai báo `static void f()`, Child cũng có `static void f()`. Đây là override?  
**Đáp án:** Không; static method hiding khi hợp lệ.

**Câu 11.** Parent và Child cùng khai báo `int value`, reference kiểu Parent trỏ Child đọc `ref.value` thường chọn field nào?  
**Đáp án:** Field Parent được chọn theo static type Parent và field lookup rules.

**Câu 12.** Private Parent field và private Child field trùng tên có phải một field không?  
**Đáp án:** Không. Hai declarations/state độc lập.

**Câu 13.** Constructors có được inherited không?  
**Đáp án:** Không. Child constructor phải gọi constructor superclass accessible theo quy tắc.

**Câu 14.** Parent chỉ có `Parent(int)`, Child không khai báo constructor. Có gì sai?  
**Đáp án:** Default Child constructor muốn implicit `super()` nhưng Parent không có no-arg accessible; compilation error.

**Câu 15.** Parent có private no-arg constructor, Child top-level bên ngoài có gọi `super()` được không?  
**Đáp án:** Không, constructor inaccessible.

**Câu 16.** Package-private member có accessible từ subclass ở package khác chỉ do `extends` không?  
**Đáp án:** Không. Phạm vi package-private bị giới hạn trong package tương ứng.

**Câu 17.** `protected` field trong Base package api có thể được subclass Child package client truy cập qua `this.field` không?  
**Đáp án:** Có nếu thỏa quy tắc protected subclass access.

**Câu 18.** Cũng ở Child khác package, `Base other; other.field` với protected field Base có luôn hợp lệ không?  
**Đáp án:** Không. Cross-package protected access có receiver restrictions; `Base` qualifier thường không đủ.

**Câu 19.** Parent method public bị Child override thành protected được không?  
**Đáp án:** Không; không được giảm quyền truy cập của overridden method.

**Câu 20.** Parent method protected bị Child override thành public được không?  
**Đáp án:** Có thể, nếu các rules khác (chữ ký/return/throws) phù hợp.

**Câu 21.** Một class implements interface có thể gọi private helper của interface bằng tên không?  
**Đáp án:** Không; private interface method không được kế thừa/công khai cho implementers.

**Câu 22.** Static method của interface gọi qua implementing class có hợp lệ không?  
**Đáp án:** Không theo ý nghĩa inherited member; gọi `InterfaceName.method()`.

**Câu 23.** Vì sao `private final List<String> tags` vẫn có thể bị mutate nếu Parent getter trả chính list?  
**Đáp án:** Private/final chỉ hạn chế field access/reassignment; caller nhận mutable reference có thể thay đổi list.

**Câu 24.** Lớp cha thiết kế balance bất biến không âm nên mở `protected balance` hay protected validated methods?  
**Đáp án:** Thường ưu tiên private field + protected/public domain operations có validation.

**Câu 25.** Constructor Parent gọi overridable method Child sớm có thể đọc gì?  
**Đáp án:** Child fields có thể còn default 0/null trước khi field initializers/constructor body Child chạy.

**Câu 26.** Vì sao `Parent.class.getDeclaredFields()` có thể hiển thị private fields mà Child vẫn không compile nếu truy cập field?  
**Đáp án:** Metadata/reflective inspection khác source-level member inheritance/access rights.

**Câu 27.** Member nested type public của Parent có thể được lookup qua Child không?  
**Đáp án:** Có trong điều kiện type inheritance/name lookup phù hợp, ví dụ `Child.Token`.

**Câu 28.** Kế thừa có tạo hai object Parent và Child riêng không?  
**Đáp án:** Không. `new Child()` tạo một object với superclass constructor chain và state phù hợp.

**Câu 29.** `private` fields “không được kế thừa” có nghĩa GC xóa field của Parent không?  
**Đáp án:** Không. Đó là quy tắc inheritance/access, không phải cơ chế GC.

**Câu 30.** Khi nào dùng composition thay inheritance?  
**Đáp án:** Khi A cần dùng/cộng tác với B mà không có quan hệ kiểu “A là một loại B” thật sự; composition qua reference thường linh hoạt hơn.

## 30. Tài liệu tham khảo

- Java Language Specification (Java SE 17), [`8.2 — Class Members](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.2): thành viên declared/inherited, fields, methods và member types.
- Java Language Specification, [`6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6): `private`, package-private, `protected`, `public` và protected qualified access.
- Java Language Specification, [`8.4.8 — Inheritance, Overriding, and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8): quan hệ methods inherited/overridden/hidden.
- Java Language Specification, [`8.3 — Field Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3): khai báo và hiding fields.
- Java Language Specification, [`8.8 — Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8): constructors và việc không kế thừa constructors.
- Java Language Specification, [`8.8.7.1 — Explicit Constructor Invocations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.7.1): `this(...)`, `super(...)` theo Java 17.
- Java Language Specification, [`9.4 — Abstract Methods and Interface Methods](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.4): public/default/private interface methods.
- Java Language Specification, [`9.3 — Field Declarations in Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.3): interface fields.
- Java Language Specification, [`15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): method lookup và runtime invocation.
- Java Language Specification, [`12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): phần superclass/subclass trong object initialization.

## Kết luận

**Kế thừa không đồng nghĩa subclass được truy cập trực tiếp mọi member của superclass.** Các fields, methods và member types được thừa hưởng theo loại thành viên và access rules; **private members không trở thành members dùng trực tiếp trong subclass**, nhưng private state của superclass **vẫn tồn tại** và được superclass constructors/methods quản lý trong cùng object.

Hãy luôn tách **quyền truy cập**, **kế thừa member**, **overriding/hiding** và **dispatch lúc chạy**. Private method không bị override; fields không override; static methods hide thay vì dynamic override; constructors không được kế thừa; `protected` có các ràng buộc package và kiểu receiver. Một thiết kế bền vững thường đặt representation ở `private`, mở **public/protected behavior với hợp đồng rõ ràng**, dùng `@Override` khi thực sự ghi đè, và chỉ cung cấp extension points mà superclass có thể bảo vệ đúng invariants của mình.
