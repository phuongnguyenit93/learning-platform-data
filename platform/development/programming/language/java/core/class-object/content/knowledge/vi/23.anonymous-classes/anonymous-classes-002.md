# Lớp vô danh: mở rộng một lớp hoặc hiện thực một interface trong Java 17+

**Lớp vô danh (anonymous class)** cho phép định nghĩa **một lớp không có tên trong source code** đồng thời tạo instance của nó bằng một **class instance creation expression**. Lớp vô danh dùng để:

1. **Mở rộng (extend) một class** — có thể là class thường hoặc abstract class, miễn class đó không `final` và có constructor truy cập được, đồng thời thỏa các quy tắc kế thừa.
2. **Hiện thực (implement) một interface** — cung cấp các methods còn abstract theo contract của interface.

Hai mẫu quan trọng nhất:

~~~java
Runnable work = new Runnable() {
    @Override
    public void run() {
        System.out.println("running");
    }
};
~~~

~~~java
Animal animal = new Animal("Milo") {
    @Override
    String sound() {
        return "woof";
    }
};
~~~

Trong mẫu thứ nhất, class vô danh **implements Runnable**, còn trong mẫu thứ hai, class vô danh **extends Animal**. Cả hai tạo một **đối tượng thuộc lớp vô danh** chứ không phải đối tượng thuần túy của interface/abstract class. Caller thường giữ reference qua **kiểu cha (supertype)**.

Bài thuộc **Java Core — class-object / Lớp vô danh**, áp dụng **Java 17+**. Các chương trình hoàn chỉnh có tên file, lệnh `javac`/`java` và stdout dự kiến. Những đoạn cố ý gây compile error được comment để phân biệt với mã chạy.

## 1. Mục tiêu

Học xong, bạn có thể:

- Nhận ra cú pháp `new Interface() { ... }` và `new Base(args) { ... }`.
- Hiểu anonymous class là **class thực sự**, có runtime Class metadata nhưng không có simple name trong source.
- Phân biệt class được khai báo và object instance được tạo bởi expression.
- Biết một anonymous class **extends một class hoặc implements một interface trực tiếp** theo type được nêu ở đầu expression.
- Hiểu vì sao không thể `new Interface()` hoặc `new AbstractClass()` mà không cung cấp body thực thi các abstract methods.
- Sử dụng `@Override`, interface method contracts và dynamic dispatch.
- Gọi super constructor bằng constructor arguments ở expression.
- Hiểu anonymous class không thể khai báo constructor có tên, nhưng có thể dùng instance initializer.
- Biết anonymous class có fields/methods riêng, nhưng reference kiểu cha không gọi được methods ngoài contract.
- Dùng anonymous class trong callback, `Comparator`, `Runnable`, strategy objects hoặc custom overrides.
- Phân biệt `this`, `super` và `Outer.this`.
- Hiểu capture local variables/parameters `final` hoặc `effectively final`.
- Phân biệt sửa mutable captured object với gán lại reference.
- Phân biệt anonymous class và **lambda expression**.
- Biết anonymous class khác **local named class**, **member inner class** và **static nested class**.
- Nắm giới hạn: `final` class, `sealed` type, type/access restrictions, checked exceptions.
- Dùng generics và diamond syntax đúng với Java 17.
- Hiểu type identity, equality, scope, memory retention và thread safety.
- Viết kiểm thử xác minh dispatch, capture, constructor args và callback behavior.

## 2. Lớp vô danh thực chất là gì?

Ở một declaration thường, ta đặt tên cho class:

~~~java
class NamedRunner implements Runnable {
    @Override
    public void run() {
        System.out.println("run");
    }
}
~~~

Sau đó tạo object:

~~~java
Runnable r = new NamedRunner();
~~~

Lớp vô danh gộp việc khai báo một subclass/implementation không có tên vào expression tạo instance:

~~~java
Runnable r = new Runnable() {
    @Override
    public void run() {
        System.out.println("run");
    }
};
~~~

Class runtime của `r` không phải interface `Runnable` (interface không thể được instantiate trực tiếp). Nó là một **generated anonymous implementation class** của Runnable.

### Vẽ quan hệ

~~~text
     Interface Runnable
             ^
             | implements
             |
    Anonymous class #1
             ^
             | instance-of
             |
          object r
~~~

Nếu dùng `new Base(...) { ... }`, anonymous class có superclass là Base. Một Java class có thể kế thừa tối đa **một superclass**, nhưng có thể implements multiple interfaces qua khai báo class bình thường; cú pháp anonymous class chỉ chọn **một kiểu trực tiếp** trong phần trước body (class hoặc interface).

## 3. Chương trình đầu tiên: implements interface

Tạo **`AnonymousRunnableDemo.java`**:

~~~java
public class AnonymousRunnableDemo {
    public static void main(String[] args) {
        Runnable task = new Runnable() {
            @Override
            public void run() {
                System.out.println("Hello from anonymous class");
            }
        };

        task.run();

        System.out.println("anonymous=" +
                task.getClass().isAnonymousClass());
        System.out.println("runnable=" +
                (task instanceof Runnable));
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousRunnableDemo.java
java AnonymousRunnableDemo
~~~

Stdout:

~~~text
Hello from anonymous class
anonymous=true
runnable=true
~~~

Dòng `new Runnable() { ... }` tạo một object của anonymous class thực thi Runnable. Dòng `task.run()` dispatch đến method run override trong anonymous implementation.

## 4. Cú pháp implements một interface

Mẫu đầy đủ:

~~~java
InterfaceType variable = new InterfaceType() {
    @Override
    public ReturnType method(Parameters parameters) {
        // implementation
    }
};
~~~

Lưu ý:

- `InterfaceType` là interface type, **không phải constructor** thực sự có thể gọi của interface.
- Dấu `()` trong `new InterfaceType()` không truyền arguments vào một interface constructor; interface không có instance constructors như classes.
- Body `{ ... }` là class body của anonymous class, nơi bạn triển khai required methods.
- Sau đóng body `}`, một expression statement/variable initializer thường có dấu chấm phẩy `;`.
- Interface có một hay nhiều abstract methods đều có thể được anonymous class thực thi, miễn triển khai đầy đủ và đúng signature.
- Nếu interface đã có `default` methods, anonymous class có thể kế thừa default behavior hoặc override.

### Một interface, nhiều methods

Ví dụ một interface domain:

~~~java
interface Formatter {
    String format(String value);

    boolean accepts(String value);
}
~~~

Anonymous implementation phải cung cấp cả `format` và `accepts`, trừ khi method có default implementation hoặc được giải quyết qua type rules khác.

## 5. Chương trình chạy: interface có nhiều abstract methods

Tạo **`AnonymousFormatterDemo.java`**:

~~~java
public class AnonymousFormatterDemo {
    interface Formatter {
        boolean accepts(String input);
        String format(String input);
    }

    public static void main(String[] args) {
        Formatter formatter = new Formatter() {
            @Override
            public boolean accepts(String input) {
                return input != null && !input.isBlank();
            }

            @Override
            public String format(String input) {
                if (!accepts(input)) {
                    return "INVALID";
                }
                return input.strip().toUpperCase(
                        java.util.Locale.ROOT);
            }
        };

        System.out.println(formatter.format(" java "));
        System.out.println(formatter.format("  "));
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousFormatterDemo.java
java AnonymousFormatterDemo
~~~

Stdout:

~~~text
JAVA
INVALID
~~~

Interface Formatter không phải functional interface vì có hai abstract methods, nhưng anonymous class vẫn implements được. Lambda không thể trực tiếp hiện thực một interface với hai abstract methods không liên quan; anonymous class có phạm vi sử dụng rộng hơn ở điểm này.

## 6. Anonymous class có thể extend một abstract class

Khi có abstract base class:

~~~java
abstract class Shape {
    abstract double area();
}
~~~

Bạn không thể viết `new Shape()` mà không có anonymous subclass body vì Shape là abstract. Nhưng có thể:

~~~java
Shape shape = new Shape() {
    @Override
    double area() {
        return 10.0;
    }
};
~~~

Expression tạo **một instance của một concrete anonymous subclass of Shape**.

### Dynamic dispatch

Khi gọi `shape.area()`, biến `shape` có declared type Shape; JVM chọn implementation của actual anonymous subclass theo dynamic dispatch. Đây là tính đa hình bình thường của Java OOP, không phải exception riêng cho anonymous class.

## 7. Chương trình chạy: extends abstract class

Tạo **`AnonymousShapeDemo.java`**:

~~~java
public class AnonymousShapeDemo {
    static abstract class Shape {
        abstract int area();
    }

    public static void main(String[] args) {
        Shape rectangle = new Shape() {
            @Override
            int area() {
                return 3 * 4;
            }
        };

        Shape square = new Shape() {
            @Override
            int area() {
                return 5 * 5;
            }
        };

        System.out.println("rectangle=" + rectangle.area());
        System.out.println("square=" + square.area());
        System.out.println("different objects=" +
                (rectangle != square));
        System.out.println("same class=" +
                (rectangle.getClass() == square.getClass()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousShapeDemo.java
java AnonymousShapeDemo
~~~

Stdout:

~~~text
rectangle=12
square=25
different objects=true
same class=false
~~~

Hai expression `new Shape() { ... }` nằm ở **hai source locations** khác nhau, nên là **hai anonymous class declarations khác nhau**, không chỉ hai objects từ một declaration. Vì vậy `getClass() ==` false trong ví dụ.

## 8. Extends concrete class để thay đổi behavior

Lớp cha **không bắt buộc abstract**. Một anonymous subclass có thể override virtual method của một concrete class miễn class không final và method có thể override.

~~~java
class Greeter {
    String message() {
        return "Hello";
    }
}

Greeter custom = new Greeter() {
    @Override
    String message() {
        return "Xin chao";
    }
};
~~~

`custom` vẫn được sử dụng dưới declared type Greeter. `custom.message()` gọi override ở anonymous subclass.

### Khi nào hữu ích?

- Thay một phần behavior của abstract/concrete base có contract rõ.
- Tạo một customization cục bộ thay vì khai báo named subclass ở nơi khác.
- Viết test double hoặc callback adapter nhỏ.

Nhưng nếu override nhiều methods hoặc behavior phức tạp, một named class thường dễ debug/test/đọc hơn.

## 9. Chương trình chạy: override concrete method

Tạo **`AnonymousConcreteSubclassDemo.java`**:

~~~java
public class AnonymousConcreteSubclassDemo {
    static class Greeter {
        String message(String name) {
            return "Hello, " + name;
        }
    }

    public static void main(String[] args) {
        Greeter standard = new Greeter();

        Greeter custom = new Greeter() {
            @Override
            String message(String name) {
                return "Xin chao, " + name;
            }
        };

        System.out.println(standard.message("Mai"));
        System.out.println(custom.message("Mai"));
        System.out.println("custom is subclass=" +
                (custom.getClass() != Greeter.class));
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousConcreteSubclassDemo.java
java AnonymousConcreteSubclassDemo
~~~

Stdout:

~~~text
Hello, Mai
Xin chao, Mai
custom is subclass=true
~~~

`new Greeter() { ... }` là object của anonymous subclass, không phải Greeter base instance thuần. Nó vẫn là `instanceof Greeter`, vì subclass inherits base type.

## 10. Một anonymous class declaration có thể tạo nhiều instances không?

Tên của anonymous class không có simple name để caller viết `new AnonymousClassName()` ở nơi khác. Tuy nhiên, **cùng source expression** có thể được thực thi nhiều lần, ví dụ bên trong factory method:

~~~java
static Runnable newTask(String message) {
    return new Runnable() {
        @Override
        public void run() {
            System.out.println(message);
        }
    };
}
~~~

Mỗi lần gọi `newTask` tạo một object mới của **cùng một anonymous class definition** ở vị trí source đó. Khác với ví dụ hai `new Shape() { ... }` ở hai source locations, trường hợp này có cùng runtime Class metadata cho cùng declaration trong cùng defining-class-loader context.

## 11. Chương trình chạy: cùng anonymous class, nhiều objects

Tạo **`AnonymousFactoryDemo.java`**:

~~~java
public class AnonymousFactoryDemo {
    static Runnable newTask(String message) {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(message);
            }
        };
    }

    public static void main(String[] args) {
        Runnable a = newTask("A");
        Runnable b = newTask("B");

        System.out.println("same object=" + (a == b));
        System.out.println("same class=" +
                (a.getClass() == b.getClass()));

        a.run();
        b.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousFactoryDemo.java
java AnonymousFactoryDemo
~~~

Stdout:

~~~text
same object=false
same class=true
A
B
~~~

Hai anonymous instances khác nhau có captured value message khác nhau, nhưng cùng class definition được tạo tại một source location.

## 12. Constructor của superclass trong anonymous class

Anonymous class **không có tên để khai báo constructor riêng**. Nếu extends một class có constructor cần arguments, truyền các arguments ở expression:

~~~java
Base value = new Base("A", 7) {
    @Override
    void execute() {
        // ...
    }
};
~~~

Việc tạo object sẽ gọi **một superclass constructor phù hợp** với arguments theo rules của Java class instance creation và constructor resolution.

Nhưng bạn **không** khai báo:

~~~java
// Trong body anonymous class:
// Anonymous(...) { ... } // Không có tên class để định nghĩa constructor.
~~~

Nếu cần initialization riêng cho fields của anonymous class, có thể dùng field initializers hoặc instance initializer block. Nếu initialization phức tạp, named subclass/copy factory thường rõ hơn.

## 13. Chương trình chạy: superclass constructor parameters

Tạo **`AnonymousConstructorDemo.java`**:

~~~java
public class AnonymousConstructorDemo {
    static abstract class Job {
        private final String label;

        Job(String label) {
            this.label = label;
            System.out.println("base constructor:" + label);
        }

        String label() {
            return label;
        }

        abstract String result();
    }

    public static void main(String[] args) {
        Job job = new Job("compile") {
            @Override
            String result() {
                return label() + ":done";
            }
        };

        System.out.println(job.result());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousConstructorDemo.java
java AnonymousConstructorDemo
~~~

Stdout:

~~~text
base constructor:compile
compile:done
~~~

`new Job("compile") { ... }` gọi Job(String) trước khi object hoàn tất initialization. Anonymous subclass override method result và thừa hưởng label().

**Cảnh báo constructor override dispatch:** Nếu superclass constructor gọi một overridable method, call có thể dispatch đến subclass override **trước khi subclass fields được init đầy đủ**. Tránh pattern đó.

## 14. Instance initializer trong anonymous class

Anonymous class có thể khai báo instance initializer:

~~~java
Runnable runner = new Runnable() {
    private int runs;

    {
        runs = 10;
    }

    @Override
    public void run() {
        System.out.println(++runs);
    }
};
~~~

Instance initializer chạy khi instance được tạo, theo Java initialization order, và trước khi instance được sử dụng bình thường. Nó **không thay thế** superclass constructor.

### Chương trình chạy

Tạo **`AnonymousInitializerDemo.java`**:

~~~java
public class AnonymousInitializerDemo {
    public static void main(String[] args) {
        Runnable task = new Runnable() {
            private int count;

            {
                count = 10;
                System.out.println("initialized");
            }

            @Override
            public void run() {
                count++;
                System.out.println("count=" + count);
            }
        };

        task.run();
        task.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousInitializerDemo.java
java AnonymousInitializerDemo
~~~

Stdout:

~~~text
initialized
count=11
count=12
~~~

Anonymous class có instance state riêng. Không cần lambda hoặc static globals để quản lý counter nếu state gắn với mỗi callback instance.

## 15. Anonymous class có fields, helper methods và private state

Body của anonymous class có thể chứa members hợp lệ giống một class thông thường: instance fields, methods, initializers và (theo Java version) static declarations, miễn tuân thủ context rules.

Ví dụ:

~~~java
Runnable task = new Runnable() {
    private int count;

    private void increment() {
        count++;
    }

    @Override
    public void run() {
        increment();
        System.out.println(count);
    }
};
~~~

Client có reference `Runnable` sẽ gọi được `run()`, không tự gọi được `increment()` hay truy cập count vì members đó không nằm trong public API của Runnable.

**Quan trọng:** Có anonymous-class-only method không có nghĩa caller tự động nhìn thấy method qua declared supertype.

## 16. Chương trình chạy: fields và helpers nội bộ

Tạo **`AnonymousStateDemo.java`**:

~~~java
public class AnonymousStateDemo {
    static Runnable counter() {
        return new Runnable() {
            private int count;

            private void next() {
                count++;
            }

            @Override
            public void run() {
                next();
                System.out.println("call=" + count);
            }
        };
    }

    public static void main(String[] args) {
        Runnable a = counter();
        Runnable b = counter();

        a.run();
        a.run();
        b.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousStateDemo.java
java AnonymousStateDemo
~~~

Stdout:

~~~text
call=1
call=2
call=1
~~~

Mỗi anonymous instance có state `count` riêng. Hai instances không chia sẻ field count, dù được tạo bởi cùng anonymous class declaration ở factory method.

## 17. Declared type quyết định members caller gọi được

~~~java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("run");
    }

    public void extra() {
        System.out.println("extra");
    }
};
~~~

`task.extra()` **không biên dịch** vì compiler nhìn declared type Runnable, không có extra() method. Anonymous runtime object có method extra nhưng reference kiểu Runnable chỉ expose Runnable methods.

### Dùng supertype cho encapsulation

Thực tế đây thường là lợi thế: anonymous class chỉ là implementation detail; client dùng contract interface/base class. Nếu caller thật sự cần extra behavior, thêm nó vào **một interface phù hợp** hoặc dùng named class thay vì dựa vào reflection.

### Ngoại lệ hữu ích: `var` và anonymous type inference

Trong local variable inference Java 10+, `var example = new Object() { String extra() {...} };` có thể giữ inferred anonymous class type trong phạm vi biến, cho phép gọi member extra() theo typing rules. Tuy nhiên pattern này ít phù hợp public API; đừng xây hệ thống phụ thuộc anonymous-specific members từ bên ngoài method.

## 18. Ví dụ chạy: local `var` giữ anonymous-specific method

Tạo **`AnonymousVarDemo.java`**:

~~~java
public class AnonymousVarDemo {
    public static void main(String[] args) {
        var value = new Object() {
            String describe() {
                return "anonymous-only";
            }
        };

        System.out.println(value.describe());
        System.out.println("anonymous=" +
                value.getClass().isAnonymousClass());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 AnonymousVarDemo.java
java AnonymousVarDemo
~~~

Stdout:

~~~text
anonymous-only
anonymous=true
~~~

`var` suy luận anonymous class type trong local scope. Nếu đổi thành `Object value = new Object() { ... };` thì `value.describe()` không biên dịch vì Object không có describe(). Không nên nhầm inference convenience thành cơ chế công bố anonymous class type ra ngoài public API.

## 19. `@Override` kiểm tra method signature

Nên dùng `@Override` khi triển khai interface method hoặc override superclass method:

~~~java
Runnable r = new Runnable() {
    @Override
    public void run() {
        System.out.println("ok");
    }
};
~~~

Lợi ích:

- Compiler phát hiện sai method name/signature.
- Tránh tạo một method mới do typo thay vì override method dự định.
- Làm rõ polymorphic contract cho người đọc.

### Visibility khi implement interface

Interface abstract methods mặc định là public trong phần lớn trường hợp thông thường; implementation phải `public`:

~~~java
new Runnable() {
    @Override
    public void run() {
        System.out.println("ok");
    }
};
~~~

Nếu viết `void run()` thiếu public, sẽ bị compiler từ chối vì không thể giảm visibility của method public trong Runnable.

## 20. Chương trình chạy: interface với default method

Tạo **`AnonymousDefaultMethodDemo.java`**:

~~~java
public class AnonymousDefaultMethodDemo {
    interface Messenger {
        String name();

        default String message() {
            return "Hello, " + name();
        }
    }

    public static void main(String[] args) {
        Messenger messenger = new Messenger() {
            @Override
            public String name() {
                return "Mai";
            }
        };

        System.out.println(messenger.name());
        System.out.println(messenger.message());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousDefaultMethodDemo.java
java AnonymousDefaultMethodDemo
~~~

Stdout:

~~~text
Mai
Hello, Mai
~~~

Anonymous class chỉ implement `name()`; default `message()` có thể được thừa hưởng và gọi name() bằng dynamic dispatch.

## 21. `this` trong anonymous class

Bên trong instance method của anonymous class:

- `this` trỏ **chính anonymous class instance**.
- `this` **không** tự trỏ outer class object.
- Trong outer instance context, `Outer.this` chỉ enclosing outer instance nếu hợp lệ.
- `super` trỏ behavior của **superclass anonymous class** nếu extends class, không phải enclosing outer class.

Đây là khác biệt quan trọng so với lambda. Trong lambda, `this` được xử lý theo lexical enclosing context, không tạo nghĩa “anonymous callback instance” giống anonymous class body.

## 22. Phân biệt nhanh `this` với `Outer.this` khi implement interface

Anonymous class triển khai interface là **một class/instance khác** với enclosing owner. Ví dụ snippet Java 17:

~~~java
class Owner {
    private final String id = "A";

    Runnable makeTask() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(
                        this.getClass().isAnonymousClass());
                System.out.println(Owner.this.id);
            }
        };
    }
}
~~~

Nếu tạo `new Owner().makeTask().run()` trong chương trình phù hợp, hai dòng lần lượt là `true` và `A`. `this` chỉ callback instance, còn `Owner.this` chỉ instance của lớp bao ngoài. **Enclosing** khác **superclass**: anonymous callback này implements `Runnable`, không extends `Owner`.

Bài “Ý nghĩa this và truy cập đối tượng bao ngoài” đào sâu nhiều tầng nesting, shadowing và lifecycle. Ở đây phép đối chiếu ngắn chỉ để bảo vệ cách hiểu extends/implements.

## 23. `super` khi anonymous class extends class

Giả sử concrete superclass có method greet():

~~~java
class Greeter {
    String greet() {
        return "Hello";
    }
}

Greeter custom = new Greeter() {
    @Override
    String greet() {
        return super.greet() + " Java";
    }
};
~~~

Trong override, `super.greet()` gọi implementation của superclass Greeter theo Java rules. Nó không gọi method của enclosing outer object.

### Chương trình chạy

Tạo **`AnonymousSuperDemo.java`**:

~~~java
public class AnonymousSuperDemo {
    static class Greeter {
        String greet() {
            return "Hello";
        }
    }

    public static void main(String[] args) {
        Greeter custom = new Greeter() {
            @Override
            String greet() {
                return super.greet() + " Java";
            }
        };

        System.out.println(custom.greet());
        System.out.println("superclass Greeter=" +
                (custom.getClass().getSuperclass() ==
                        Greeter.class));
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousSuperDemo.java
java AnonymousSuperDemo
~~~

Stdout:

~~~text
Hello Java
superclass Greeter=true
~~~

Anonymous class extends Greeter và có thể dùng protected/accessible inherited behavior theo inheritance rules.

## 24. Capture local variables và parameters

Anonymous class khai báo trong method/block có thể dùng enclosing method locals/parameters nếu **final hoặc effectively final**:

~~~java
static Runnable task(String name) {
    int repeat = 2;

    return new Runnable() {
        @Override
        public void run() {
            for (int i = 0; i < repeat; i++) {
                System.out.println(name);
            }
        }
    };
}
~~~

`name` và `repeat` không bị reassigned; code hợp lệ. `repeat` là captured primitive value, `name` là captured String reference tới immutable text.

Lưu ý captured local variables có thể được dùng sau khi method đã return, vì anonymous object còn được caller giữ. Compiler/JVM thực hiện semantics capture chứ không phụ thuộc direct access vào một stack frame đã kết thúc.

## 25. Chương trình chạy: capture effectively-final locals

Tạo **`AnonymousCaptureDemo.java`**:

~~~java
public class AnonymousCaptureDemo {
    static Runnable task(String text) {
        int times = 2;

        return new Runnable() {
            @Override
            public void run() {
                for (int i = 0; i < times; i++) {
                    System.out.println(text);
                }
            }
        };
    }

    public static void main(String[] args) {
        Runnable a = task("A");
        Runnable b = task("B");

        a.run();
        b.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousCaptureDemo.java
java AnonymousCaptureDemo
~~~

Stdout:

~~~text
A
A
B
B
~~~

Mỗi instance capture giá trị text từ invocation tạo nó. `times` là effectively final dù không ghi `final`.

## 26. Vì sao không được gán lại captured local?

~~~java
static Runnable invalid() {
    int count = 1;
    count++;

    return new Runnable() {
        @Override
        public void run() {
            // System.out.println(count); // Compile error nếu bỏ comment.
            System.out.println("count unavailable");
        }
    };
}
~~~

`count++` làm biến mất effectively final. Nếu anonymous class đọc count, javac từ chối capture.

### Giải pháp

- Nếu muốn một value cố định, tính toán trước rồi capture vào một biến **không được gán lại**.
- Nếu muốn mutable state riêng cho anonymous object, khai báo field bên trong anonymous class.
- Nếu nhiều instances cần chia sẻ mutable state có kiểm soát, truyền một explicit state holder có synchronization/ownership phù hợp.
- Không dùng một mảng một phần tử chỉ để “lách” effectively final mà bỏ qua thread-safety và API clarity.

## 27. Capture mutable reference không đóng băng object

~~~java
java.util.List<String> names = new java.util.ArrayList<>();

Runnable r = new Runnable() {
    @Override
    public void run() {
        names.add("Java");
    }
};
~~~

`names` không bị gán lại nên effectively final; nhưng `ArrayList` object vẫn mutable. Khi run() gọi, List thay đổi.

### Chương trình chạy

Tạo **`AnonymousMutableCaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class AnonymousMutableCaptureDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();

        Runnable append = new Runnable() {
            @Override
            public void run() {
                names.add("Java");
            }
        };

        append.run();
        append.run();

        System.out.println(names);
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousMutableCaptureDemo.java
java AnonymousMutableCaptureDemo
~~~

Stdout:

~~~text
[Java, Java]
~~~

**Effectively final ≠ immutable ≠ thread-safe.** Quy tắc capture chỉ hạn chế reassignment của variable, không cấm thay đổi mutable object mà nó trỏ tới.

## 28. Anonymous class vs lambda: cú pháp

Với functional interface:

~~~java
Runnable anonymous = new Runnable() {
    @Override
    public void run() {
        System.out.println("A");
    }
};

Runnable lambda = () -> System.out.println("B");
~~~

Cả hai có thể dùng như Runnable callback. Nhưng chúng không luôn tương đương về ngữ nghĩa:

- Anonymous class định nghĩa một class body; lambda là **lambda expression** được type-check dựa trên target functional interface.
- Anonymous `this` là anonymous object; lambda `this` là lexical enclosing receiver (nếu có).
- Anonymous class có thể implement interface **nhiều abstract methods**; lambda cần functional interface.
- Anonymous class có thể extend concrete/abstract class; lambda không extend arbitrary class.
- Anonymous class có instance fields, instance initializers và helper methods; lambda body không khai báo anonymous class body cùng kiểu.
- Cơ chế runtime Class metadata/caching/identity của lambda không nên được giả định giống anonymous class.

## 29. Chương trình chạy: callback anonymous và lambda

Tạo **`AnonymousVsLambdaDemo.java`**:

~~~java
public class AnonymousVsLambdaDemo {
    static void execute(Runnable runnable) {
        runnable.run();
    }

    public static void main(String[] args) {
        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("anonymous");
            }
        };

        Runnable lambda = () -> System.out.println("lambda");

        execute(anonymous);
        execute(lambda);
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousVsLambdaDemo.java
java AnonymousVsLambdaDemo
~~~

Stdout:

~~~text
anonymous
lambda
~~~

Trong trường hợp chỉ chạy một dòng và không cần state/helpers/inheritance, lambda thường ngắn và rõ. Với nhiều methods, constructor arguments của superclass hoặc class body cần fields, anonymous class vẫn hữu ích.

## 30. `this` khác nhau giữa anonymous class và lambda

Không thể thay `new Runnable() { ... }` bằng `() -> ...` chỉ dựa trên việc target type là `Runnable`. Kiểm tra **receiver và type contract**:

| Bên trong callback | Anonymous class | Lambda |
| --- | --- | --- |
| `this` | Anonymous instance hiện tại | Lexical enclosing instance (nếu có) |
| `Outer.this` | Enclosing Outer nếu nằm trong context hợp lệ | Cũng theo lexical enclosing context |
| Instance field riêng do callback khai báo | Có trong anonymous class body | Không có class body riêng để khai báo field |
| `super.method()` | Superclass của anonymous class | `super` theo lexical enclosing class |
| Trong static method | Anonymous instance vẫn có `this` | Không có enclosing `this` để dùng |

Với việc **implements interface** đang học, điều cần xác định trước tiên là API muốn một object mang state riêng hay chỉ một chức năng của functional interface. Khi body của anonymous class gọi `this` để giữ/huỷ đăng ký callback, chuyển sang lambda có thể đổi đích reference. Bài so sánh anonymous–lambda chuyên sâu có ví dụ chạy và stdout cho từng ngữ cảnh; không nên nhân bản chương trình đó ở đây.

## 31. Anonymous class vs local named class

**Local named class:**

~~~java
void method() {
    class LocalRunner implements Runnable {
        public void run() {
            System.out.println("run");
        }
    }

    Runnable a = new LocalRunner();
    Runnable b = new LocalRunner();
}
~~~

**Anonymous class:**

~~~java
void method() {
    Runnable a = new Runnable() {
        public void run() {
            System.out.println("run");
        }
    };
}
~~~

LocalRunner có **tên trong block**, có thể khai báo explicit constructors và tạo nhiều instances qua `new LocalRunner()`. Anonymous class không có class name trong source; muốn tạo cùng type nhiều lần thường đặt expression trong một factory method chạy nhiều lần.

Nếu implementation dài hoặc cần tái sử dụng trong một block, local named class rõ hơn. Nếu chỉ one-off customization tại một expression, anonymous class có thể phù hợp.

## 32. Anonymous class extends abstract adapter class

Một số APIs/frameworks định nghĩa adapter base class có concrete/default implementations để client chỉ cần override method quan tâm:

~~~java
abstract class ListenerAdapter {
    void onStart() {}
    void onStop() {}
}
~~~

Anonymous subclass có thể override đúng hook:

~~~java
ListenerAdapter listener = new ListenerAdapter() {
    @Override
    void onStart() {
        System.out.println("started");
    }
};
~~~

Đây là ví dụ về **extends class**, không phải implements interface. Hãy phân biệt interface `default` methods với concrete methods của adapter superclass.

### Chương trình chạy

Tạo **`AnonymousAdapterDemo.java`**:

~~~java
public class AnonymousAdapterDemo {
    static class ListenerAdapter {
        void onStart() {
        }

        void onStop() {
        }
    }

    public static void main(String[] args) {
        ListenerAdapter listener = new ListenerAdapter() {
            @Override
            void onStart() {
                System.out.println("started");
            }
        };

        listener.onStart();
        listener.onStop();
        System.out.println("completed");
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousAdapterDemo.java
java AnonymousAdapterDemo
~~~

Stdout:

~~~text
started
completed
~~~

`onStop()` được kế thừa từ base class nên không in gì, nhưng invocation hợp lệ.

## 33. Polymorphism: declared type vs runtime type

Đoạn:

~~~java
Shape shape = new Shape() {
    @Override
    double area() {
        return 5;
    }
};
~~~

có ba tầng:

1. `Shape` là **declared type** của reference variable.
2. `new Shape() { ... }` là **anonymous subclass declaration + instance creation**.
3. `shape.area()` dispatch đến implementation trong runtime anonymous subclass.

Dynamic dispatch không dựa vào tên biến hay tên file, mà dựa vào actual receiver class và override resolution.

### `instanceof`

Anonymous subclass instance cũng là instance của supertype:

~~~java
System.out.println(shape instanceof Shape); // true
~~~

Bạn không thể viết `shape instanceof AnonymousClassName` vì không có source name cho anonymous class.

## 34. Object identity và equality

Nếu có hai distinct expressions:

~~~java
Runnable a = new Runnable() { public void run() {} };
Runnable b = new Runnable() { public void run() {} };
~~~

`a == b` false; hai `new` expressions tạo objects khác nhau. Mỗi anonymous class cũng là một runtime class declaration riêng.

Nếu anonymous class không override `equals`, Object.equals mặc định dựa trên identity. Việc hai callbacks cùng in một dòng không làm chúng equals theo value.

Không nên override equals/hashCode trên anonymous callbacks một cách tùy tiện; các APIs đăng ký/hủy callback thường dựa vào **đúng object reference** đã đăng ký. Lưu reference để unregister chính xác.

## 35. Chương trình chạy: identity và Class metadata

Tạo **`AnonymousIdentityDemo.java`**:

~~~java
public class AnonymousIdentityDemo {
    public static void main(String[] args) {
        Runnable first = new Runnable() {
            @Override
            public void run() {
            }
        };

        Runnable second = new Runnable() {
            @Override
            public void run() {
            }
        };

        System.out.println("same object=" + (first == second));
        System.out.println("same class=" +
                (first.getClass() == second.getClass()));
        System.out.println("first anonymous=" +
                first.getClass().isAnonymousClass());
        System.out.println("second anonymous=" +
                second.getClass().isAnonymousClass());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousIdentityDemo.java
java AnonymousIdentityDemo
~~~

Stdout:

~~~text
same object=false
same class=false
first anonymous=true
second anonymous=true
~~~

Đây là **hai anonymous class declarations ở hai source locations**, nên khác runtime Class objects. Ngược lại, factory example ở phần trước có một expression thực thi hai lần, nên Class giống nhau.

## 36. Không thể extend `final` class

Một anonymous class là một **subclass** khi expression nêu một class name. Nhưng `final` class không cho bất cứ subclass nào:

~~~java
final class ImmutableValue {
}

// ImmutableValue x = new ImmutableValue() { }; // Compile error.
~~~

Bạn vẫn được tạo instance của final class bình thường:

~~~java
ImmutableValue x = new ImmutableValue();
~~~

Chỉ phần anonymous subclass body `{ ... }` mới đòi subclassing và bị cấm.

### Vì sao thường gặp với String?

`String` là final. Bạn không thể `new String("A") { ... }` để override String methods. Nếu cần behavior khác, dùng composition/helper/service thay vì inheritance.

## 37. `sealed` classes và interfaces trong Java 17

Java 17 hỗ trợ sealed types hạn chế những direct subclasses/implementations được phép. Anonymous class không có source-level simple class name để liệt kê theo cách thông thường trong permits clause.

Ví dụ conceptual:

~~~java
sealed interface Result permits Success, Failure {}

final class Success implements Result {}

final class Failure implements Result {}

// Result r = new Result() { }; // Không được làm direct anonymous implementation.
~~~

Nếu muốn tạo result theo permitted model, instantiate một permitted concrete class, hoặc thiết kế non-sealed extension point trong hierarchy nếu domain cần cho phép extensions.

**Đừng giả định:** “Vì anonymous class không có tên nên nó được miễn phép từ sealed restrictions.” Nó vẫn là một direct subclass/implementation trong hệ thống type rules.

## 38. Abstract methods và compile-time obligations

Khi extends abstract class với nhiều abstract methods, anonymous class phải cung cấp **đầy đủ concrete implementations** chưa được superclass hierarchy giải quyết.

~~~java
abstract class Converter {
    abstract String encode(String s);
    abstract String decode(String s);
}
~~~

Anonymous subclass:

~~~java
Converter c = new Converter() {
    @Override
    String encode(String s) {
        return s.toUpperCase(java.util.Locale.ROOT);
    }

    @Override
    String decode(String s) {
        return s.toLowerCase(java.util.Locale.ROOT);
    }
};
~~~

Nếu thiếu `decode`, compiler từ chối vì anonymous class phải là concrete class được instantiate. Anonymous class không cho bạn gắn modifier `abstract` rồi tạo object abstract.

## 39. Chương trình chạy: implement toàn bộ abstract contract

Tạo **`AnonymousConverterDemo.java`**:

~~~java
public class AnonymousConverterDemo {
    static abstract class Converter {
        abstract String encode(String text);
        abstract String decode(String text);
    }

    public static void main(String[] args) {
        Converter converter = new Converter() {
            @Override
            String encode(String text) {
                return text.toUpperCase(java.util.Locale.ROOT);
            }

            @Override
            String decode(String text) {
                return text.toLowerCase(java.util.Locale.ROOT);
            }
        };

        System.out.println(converter.encode("Java"));
        System.out.println(converter.decode("JAVA"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousConverterDemo.java
java AnonymousConverterDemo
~~~

Stdout:

~~~text
JAVA
java
~~~

Abstract class cũng có thể chứa concrete methods và fields mà anonymous subclass kế thừa.

## 40. Anonymous class có thể implements hơn một interface trực tiếp không?

Một anonymous class expression có **một type trong phần `new Type(...)`**. Không có cú pháp:

~~~java
// new Runnable(), AutoCloseable() { ... } // Không tồn tại.
~~~

Nếu cần object implements cả Runnable và AutoCloseable, hãy định nghĩa một named interface kế thừa cả hai:

~~~java
interface ManagedTask extends Runnable, AutoCloseable {
}
~~~

Rồi tạo anonymous implementation:

~~~java
ManagedTask task = new ManagedTask() {
    @Override
    public void run() {
        System.out.println("run");
    }

    @Override
    public void close() {
        System.out.println("close");
    }
};
~~~

Anonymous class có direct superinterface ManagedTask, mà ManagedTask kế thừa Runnable và AutoCloseable. Vì vậy anonymous object có thể implement **nhiều interface contracts thông qua một interface type**; giới hạn là phần `new` nêu một type, không cho liệt kê nhiều trực tiếp.

## 41. Chương trình chạy: interface extends nhiều interfaces

Tạo **`AnonymousMultipleContractsDemo.java`**:

~~~java
public class AnonymousMultipleContractsDemo {
    interface ManagedTask extends Runnable, AutoCloseable {
    }

    public static void main(String[] args) throws Exception {
        ManagedTask task = new ManagedTask() {
            @Override
            public void run() {
                System.out.println("work");
            }

            @Override
            public void close() {
                System.out.println("closed");
            }
        };

        System.out.println("runnable=" +
                (task instanceof Runnable));
        System.out.println("closeable=" +
                (task instanceof AutoCloseable));
        task.run();
        task.close();
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousMultipleContractsDemo.java
java AnonymousMultipleContractsDemo
~~~

Stdout:

~~~text
runnable=true
closeable=true
work
closed
~~~

Một object đáp ứng hai contracts nhờ interface ManagedTask extends cả hai. Nếu một API yêu cầu một nominal intersection type phức tạp, named interface thường rõ ràng và có thể dùng cho public API hơn.

## 42. Interface vs superclass constructors

Cú pháp dễ giống nhưng semantics khác:

~~~java
Runnable task = new Runnable() {
    public void run() {
    }
};
~~~

`Runnable` là interface và không có instance constructor arguments. Anonymous class có superclass Object và implements Runnable.

~~~java
Base task = new Base(42) {
    @Override
    void execute() {
    }
};
~~~

`Base` là class; `Base(42)` chọn accessible superclass constructor thích hợp. Anonymous subclass extends Base.

### Constructor selection errors

Nếu Base chỉ có `Base(int)`, viết `new Base() { ... }` sẽ lỗi vì không có accessible no-arg constructor. Sửa bằng arguments phù hợp hoặc dùng named factory.

## 43. Generic interfaces với anonymous implementation

Anonymous class hỗ trợ parameterized target interface:

~~~java
java.util.function.Supplier<String> supplier =
        new java.util.function.Supplier<String>() {
            @Override
            public String get() {
                return "Java";
            }
        };
~~~

Không cần raw types. Compiler kiểm tra `get()` trả String. Diamond syntax có thể giảm lặp type arguments trong các trường hợp được phép của Java 17.

### Chương trình chạy

Tạo **`AnonymousGenericInterfaceDemo.java`**:

~~~java
import java.util.function.Supplier;

public class AnonymousGenericInterfaceDemo {
    public static void main(String[] args) {
        Supplier<String> words = new Supplier<String>() {
            @Override
            public String get() {
                return "Java";
            }
        };

        Supplier<Integer> number = new Supplier<>() {
            @Override
            public Integer get() {
                return 17;
            }
        };

        System.out.println(words.get());
        System.out.println(number.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 AnonymousGenericInterfaceDemo.java
java AnonymousGenericInterfaceDemo
~~~

Stdout:

~~~text
Java
17
~~~

`new Supplier<>() { ... }` với diamond là hợp lệ trong Java 17 (cú pháp diamond với anonymous class được hỗ trợ từ Java 9), nhưng phải tuân thủ những hạn chế typing của anonymous class với diamond.

## 44. Diamond anonymous class và non-private methods

Khi dùng `new GenericType<>() { ... }` trong Java 9+, compiler đặt thêm restrictions cho non-private methods declared trong anonymous class, vì các method đó cần override một method của supertype tương ứng trong những điều kiện nhất định. Tránh thêm các public/helper methods không override được một cách tùy tiện khi dùng diamond anonymous class.

An toàn, rõ nghĩa:

~~~java
java.util.function.Supplier<String> supplier =
        new java.util.function.Supplier<>() {
            @Override
            public String get() {
                return "ok";
            }

            private String helper() {
                return "internal";
            }
        };
~~~

Snippet này minh họa helper private (trong ví dụ không gọi helper), và public `get()` override method của Supplier.

Nếu cần nhiều public implementation-specific methods, một named class thường cho contract tốt hơn.

## 45. Anonymous class từ generic factory method

Một generic method có thể return anonymous implementation parameterized bởi method type parameter.

Tạo **`AnonymousGenericFactoryDemo.java`**:

~~~java
import java.util.function.Supplier;

public class AnonymousGenericFactoryDemo {
    static <T> Supplier<T> fixed(T value) {
        return new Supplier<T>() {
            @Override
            public T get() {
                return value;
            }
        };
    }

    public static void main(String[] args) {
        Supplier<String> text = fixed("Java");
        Supplier<Integer> number = fixed(17);

        System.out.println(text.get());
        System.out.println(number.get());
        System.out.println("same runtime class=" +
                (text.getClass() == number.getClass()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousGenericFactoryDemo.java
java AnonymousGenericFactoryDemo
~~~

Stdout:

~~~text
Java
17
same runtime class=true
~~~

Type erasure nghĩa cùng anonymous class declaration có cùng runtime class trong một class-loader context, ngay cả khi method type argument khác nhau. Captured value vẫn có type safety ở compile time.

## 46. Anonymous class trong static vs instance context

Một anonymous class được viết trong static method vẫn có **own instance `this`**, nhưng **không có `Outer.this`** tự nhiên của static method.

~~~java
static Runnable makeStaticTask() {
    return new Runnable() {
        @Override
        public void run() {
            System.out.println(this.getClass().isAnonymousClass());
        }
    };
}
~~~

Trong instance method:

~~~java
Runnable makeInstanceTask() {
    return new Runnable() {
        @Override
        public void run() {
            System.out.println(Outer.this.toString());
        }
    };
}
~~~

Đoạn thứ hai là snippet minh họa nằm trong class Outer. Anonymous instance và enclosing Outer instance là hai objects khác nhau.

Nếu static method cần Outer state, truyền explicit Outer reference rồi capture nó, không cố dùng `Outer.this` khi không có enclosing outer instance.

## 47. Chương trình chạy: two creation contexts

Tạo **`AnonymousContextsDemo.java`**:

~~~java
public class AnonymousContextsDemo {
    private final String id;

    AnonymousContextsDemo(String id) {
        this.id = id;
    }

    Runnable fromInstance() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println("instance:" +
                        AnonymousContextsDemo.this.id);
            }
        };
    }

    static Runnable fromStatic(String name) {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println("static:" + name);
            }
        };
    }

    public static void main(String[] args) {
        Runnable a = new AnonymousContextsDemo("A").fromInstance();
        Runnable b = fromStatic("B");

        a.run();
        b.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousContextsDemo.java
java AnonymousContextsDemo
~~~

Stdout:

~~~text
instance:A
static:B
~~~

Cả hai là anonymous Runnable objects. Khác biệt là `fromInstance` có enclosing Outer instance, `fromStatic` chỉ capture String argument name.

## 48. Không gọi overridable method trong base constructor

Một superclass constructor có thể gọi virtual method được override bởi anonymous subclass. Khi đó override chạy **trước khi anonymous subclass state hoàn tất khởi tạo**, dẫn đến giá trị mặc định không mong muốn hoặc NullPointerException.

Ví dụ anti-pattern (minh họa):

~~~java
class Base {
    Base() {
        initialize(); // Virtual call nguy hiểm trong constructor.
    }

    void initialize() {
    }
}

// Base x = new Base() {
//     private String text = "ready";
//     @Override void initialize() {
//         System.out.println(text.length()); // text có thể còn null.
//     }
// };
~~~

Dùng constructor để khởi tạo private/final base state và tránh gọi overridable methods trước khi object hoàn thành construction. Nếu cần callback, gọi nó sau khi construction hoàn tất, theo API rõ ràng.

**Không nhầm:** Vấn đề này không riêng anonymous classes; mọi subclass và polymorphic constructor dispatch đều có thể mắc.

## 49. Checked exceptions và anonymous methods

Khi implement interface/override superclass method, anonymous implementation phải tuân thủ `throws` contract:

~~~java
interface Loader {
    String load() throws java.io.IOException;
}
~~~

Anonymous class có thể implement:

~~~java
Loader loader = new Loader() {
    @Override
    public String load() throws java.io.IOException {
        throw new java.io.IOException("missing");
    }
};
~~~

Caller qua `Loader` phải xử lý hoặc khai báo IOException. Nếu method contract không cho checked exception tương ứng, implementation không thể tùy ý thêm checked exception rộng hơn.

### Chương trình chạy

Tạo **`AnonymousCheckedExceptionDemo.java`**:

~~~java
import java.io.IOException;

public class AnonymousCheckedExceptionDemo {
    interface Loader {
        String load() throws IOException;
    }

    public static void main(String[] args) {
        Loader loader = new Loader() {
            @Override
            public String load() throws IOException {
                throw new IOException("missing");
            }
        };

        try {
            System.out.println(loader.load());
        } catch (IOException ex) {
            System.out.println("error=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousCheckedExceptionDemo.java
java AnonymousCheckedExceptionDemo
~~~

Stdout:

~~~text
error=missing
~~~

Anonymous class không loại bỏ checked-exception rules.

## 50. Access modifiers và package/private contracts

Nếu anonymous class implements interface, method implementation phải thỏa public contract của interface. Nếu override protected method của superclass, override có thể giữ protected hoặc tăng accessibility theo rules, nhưng không giảm.

~~~java
abstract class Base {
    protected abstract String text();
}
~~~

Anonymous subclass có thể:

~~~java
Base x = new Base() {
    @Override
    protected String text() {
        return "ok";
    }
};
~~~

Truy cập `x.text()` từ code không được phép theo protected access rules vẫn có thể bị từ chối dù actual instance đã override. Declared type và access context quyết định caller nhìn thấy gì.

Một anonymous class body không thể tùy ý hạ visibility của inherited public methods.

## 51. Test double / stub nhỏ trong unit test

Một anonymous class thường hữu ích làm **test double** cho một interface nhỏ:

~~~java
interface RateProvider {
    int centsPerUnit();
}
~~~

Trong test, ta có thể tạo một stub trả giá trị cố định để kiểm tra business logic.

Tạo **`AnonymousStubDemo.java`**:

~~~java
public class AnonymousStubDemo {
    interface RateProvider {
        int centsPerUnit();
    }

    static int total(RateProvider provider, int units) {
        if (units < 0) {
            throw new IllegalArgumentException("negative units");
        }
        return Math.multiplyExact(provider.centsPerUnit(), units);
    }

    public static void main(String[] args) {
        RateProvider fake = new RateProvider() {
            @Override
            public int centsPerUnit() {
                return 250;
            }
        };

        System.out.println("total=" + total(fake, 3));
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousStubDemo.java
java AnonymousStubDemo
~~~

Stdout:

~~~text
total=750
~~~

Stub không dùng external network/database và thỏa RateProvider contract, cho phép test logic tổng tiền. Với nhiều behavior/cases, named fake class hoặc mocking framework có thể dễ duy trì hơn.

## 52. Comparator anonymous class

`Comparator<T>` là functional interface, nên có thể dùng lambda; nhưng anonymous class vẫn hợp lệ và có ích khi comparator cần helper methods hoặc state.

Tạo **`AnonymousComparatorDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class AnonymousComparatorDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>(
                List.of("Java", "Go", "Python"));

        Comparator<String> byLength = new Comparator<String>() {
            @Override
            public int compare(String a, String b) {
                return Integer.compare(a.length(), b.length());
            }
        };

        names.sort(byLength);
        System.out.println(names);
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousComparatorDemo.java
java AnonymousComparatorDemo
~~~

Stdout:

~~~text
[Go, Java, Python]
~~~

Nếu nhiều strings có cùng length, thứ tự tương đối trong sort ổn định theo List.sort contract. Code dùng Integer.compare để tránh integer subtraction overflow trong comparator tổng quát.

## 53. Anonymous class khai báo ở argument position

Bạn không nhất thiết gán anonymous instance vào biến; có thể truyền trực tiếp vào method:

~~~java
static void execute(Runnable task) {
    task.run();
}

execute(new Runnable() {
    @Override
    public void run() {
        System.out.println("direct");
    }
});
~~~

Nó vẫn tạo anonymous class instance và truyền reference value cho method. Java parameter passing luôn pass-by-value, ngay cả khi argument là anonymous object.

### Chương trình chạy

Tạo **`AnonymousArgumentDemo.java`**:

~~~java
public class AnonymousArgumentDemo {
    static void execute(Runnable task) {
        task.run();
    }

    public static void main(String[] args) {
        execute(new Runnable() {
            @Override
            public void run() {
                System.out.println("direct");
            }
        });
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousArgumentDemo.java
java AnonymousArgumentDemo
~~~

Stdout:

~~~text
direct
~~~

Với một callback rất ngắn cho functional interface, lambda cũng có thể hợp lý: `execute(() -> System.out.println("direct"));`. Chọn theo khả năng đọc và yêu cầu behavior, không chỉ số dòng.

## 54. Một anonymous class có thể gọi private outer members

Anonymous class khai báo trong **instance context** có thể truy cập private outer members theo Java nesting access rules. Nó có thể đọc/ghi mutable outer state nếu logic cho phép.

Ví dụ:

~~~java
class Wallet {
    private int cents;

    Runnable depositTask(int amount) {
        return new Runnable() {
            @Override
            public void run() {
                cents += amount;
            }
        };
    }
}
~~~

Nhưng phép cộng thẳng có thể phá invariant/overflow và không thread-safe. Một thiết kế tốt nên **delegate qua outer method validate invariant**:

~~~java
private void deposit(int amount) {
    if (amount < 0) {
        throw new IllegalArgumentException("negative");
    }
    cents = Math.addExact(cents, amount);
}
~~~

Anonymous implementation trong `depositTask` gọi `Wallet.this.deposit(amount)` thay vì sửa cents không kiểm soát.

## 55. Chương trình chạy: callback bảo vệ invariant

Tạo **`AnonymousInvariantDemo.java`**:

~~~java
public class AnonymousInvariantDemo {
    static final class Wallet {
        private int cents;

        private void deposit(int amount) {
            if (amount < 0) {
                throw new IllegalArgumentException("negative");
            }
            cents = Math.addExact(cents, amount);
        }

        Runnable depositTask(int amount) {
            return new Runnable() {
                @Override
                public void run() {
                    Wallet.this.deposit(amount);
                }
            };
        }

        int cents() {
            return cents;
        }
    }

    public static void main(String[] args) {
        Wallet wallet = new Wallet();

        wallet.depositTask(100).run();
        System.out.println("balance=" + wallet.cents());

        try {
            wallet.depositTask(-5).run();
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }

        System.out.println("after=" + wallet.cents());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousInvariantDemo.java
java AnonymousInvariantDemo
~~~

Stdout:

~~~text
balance=100
rejected=negative
after=100
~~~

Anonymous callback có thể dùng private domain logic, nhưng encapsulation đúng cần ở chính logic của Wallet.

## 56. Memory retention và callback lifecycle

Anonymous instances có thể giữ references tới captured objects và enclosing owner. Nếu registry sống lâu lưu callback mà không unregister, outer UI/controller/services có thể bị giữ reachable lâu hơn dự tính:

~~~text
long-lived event registry
         |
         v
  anonymous callback
         |
         +------> captured service
         |
         +------> enclosing owner (khi được giữ)
~~~

Java compiler/runtime có thể biểu diễn captured state bằng fields/synthetic implementation details. Không dựa vào tên field `this$0` như một API chính thức.

### Thiết kế an toàn

- Giữ reference callback đã đăng ký để unregister đúng instance.
- Dùng lifecycle `close/dispose/unsubscribe` khi API yêu cầu.
- Tránh capture outer object rộng khi chỉ cần một immutable value nhỏ.
- Dùng static helper/named class nếu không cần enclosing owner.
- Tránh suy rằng chuyển callback sang lambda tự loại bỏ retention; lambda cũng có thể capture references.

## 57. Chương trình chạy: unsubscribe đúng callback instance

Tạo **`AnonymousListenerDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class AnonymousListenerDemo {
    static final class EventBus {
        private final List<Runnable> listeners = new ArrayList<>();

        void add(Runnable listener) {
            listeners.add(listener);
        }

        void remove(Runnable listener) {
            listeners.remove(listener);
        }

        void publish() {
            for (Runnable listener : List.copyOf(listeners)) {
                listener.run();
            }
        }
    }

    public static void main(String[] args) {
        EventBus bus = new EventBus();

        Runnable listener = new Runnable() {
            @Override
            public void run() {
                System.out.println("event");
            }
        };

        bus.add(listener);
        bus.publish();

        bus.remove(listener);
        System.out.println("after unsubscribe");
        bus.publish();
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousListenerDemo.java
java AnonymousListenerDemo
~~~

Stdout:

~~~text
event
after unsubscribe
~~~

`remove(listener)` dùng reference tới đúng object đã đăng ký. Tạo `new Runnable() { ... }` khác với cùng behavior không đồng nghĩa remove được object cũ.

## 58. Thread safety của captured state

Một anonymous Runnable có thể chạy trên thread khác. Nếu nó capture mutable List/Map/counter, object đó phải đáp ứng synchronization/ownership policy thích hợp.

~~~java
java.util.List<String> list = new java.util.ArrayList<>();
Runnable task = new Runnable() {
    public void run() {
        list.add("x");
    }
};
~~~

Đây là snippet minh họa; nếu chạy đồng thời từ nhiều threads, ArrayList không đảm bảo an toàn. Effective-final rule **không phải synchronization primitive**.

### Sử dụng AtomicInteger

Tạo **`AnonymousAtomicDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AnonymousAtomicDemo {
    public static void main(String[] args) {
        AtomicInteger count = new AtomicInteger();

        Runnable increment = new Runnable() {
            @Override
            public void run() {
                count.incrementAndGet();
            }
        };

        increment.run();
        increment.run();

        System.out.println("count=" + count.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousAtomicDemo.java
java AnonymousAtomicDemo
~~~

Stdout:

~~~text
count=2
~~~

AtomicInteger có atomic increment semantics. Program này gọi hai lần tuần tự nên stdout xác định rõ; trong multithreaded design vẫn phải xét coordination/termination để đọc kết quả đúng thời điểm.

## 59. Exception trong instance initializer và constructor flow

Nếu extends một class với constructor arguments, superclass constructor được chạy theo initialization semantics trước khi anonymous subclass instance initialization hoàn tất. Instance initializer của anonymous class có thể ném runtime exception, khiến expression không trả một object thành công.

### Không publish partial object

Một anonymous subclass đang initialize không nên đăng ký `this` vào global registry trước khi hoàn tất fields/invariants; nếu initialization thất bại hoặc thread khác chạy callback sớm, state không nhất quán có thể bị quan sát.

### Không bắt buộc dùng anonymous class

Nếu creation có nhiều bước cần validation, checked exceptions hoặc resource cleanup, named class/factory thường rõ hơn. Anonymous class nên giữ quy mô nhỏ và behavior có tính địa phương.

## 60. Serialization không được đảm bảo tự động

Một anonymous class instance có thể được giữ trong object graph, nhưng không nên mặc định nó `Serializable`:

- Implements `Runnable` không tự implements `Serializable`.
- Captured/enclosing references có thể không serializable.
- Generated anonymous class names có thể không ổn định khi code thay đổi.
- Phân phối serialization format phụ thuộc API/framework contract.

Nếu cần persist một callback/job/config, thường lưu **data/command DTO rõ ràng** rồi tái tạo behavior từ named types; không serialize arbitrary anonymous runtime implementations tùy tiện.

## 61. Reflect metadata của anonymous class

Một anonymous class object có Class metadata:

- `getClass().isAnonymousClass()` thường true.
- `getClass().getSimpleName()` thường là empty string đối với anonymous class.
- `getClass().getSuperclass()` cho biết superclass; anonymous implementation of interface thường có superclass Object.
- `getClass().getInterfaces()` cho biết trực tiếp implemented interfaces theo class metadata.
- `getEnclosingClass()`/`getEnclosingMethod()` có thể mô tả lexical declaration location.

**Quan trọng:** Reflection metadata không thay việc compiler dùng declared type để kiểm tra method accessibility. Đừng parse generated class names để làm logic production.

## 62. Chương trình chạy: reflection phân biệt implements và extends

Tạo **`AnonymousMetadataDemo.java`**:

~~~java
public class AnonymousMetadataDemo {
    static class Base {
    }

    public static void main(String[] args) {
        Runnable runnable = new Runnable() {
            @Override
            public void run() {
            }
        };

        Base subclass = new Base() {
        };

        System.out.println("runnable anonymous=" +
                runnable.getClass().isAnonymousClass());
        System.out.println("runnable superclass Object=" +
                (runnable.getClass().getSuperclass() ==
                        Object.class));
        System.out.println("runnable interface Runnable=" +
                (runnable.getClass().getInterfaces()[0] ==
                        Runnable.class));

        System.out.println("subclass anonymous=" +
                subclass.getClass().isAnonymousClass());
        System.out.println("subclass superclass Base=" +
                (subclass.getClass().getSuperclass() ==
                        Base.class));
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousMetadataDemo.java
java AnonymousMetadataDemo
~~~

Stdout:

~~~text
runnable anonymous=true
runnable superclass Object=true
runnable interface Runnable=true
subclass anonymous=true
subclass superclass Base=true
~~~

Mỗi anonymous class vẫn có runtime type metadata thật, dù không thể gọi tên class đó trong source code từ nơi khác.

## 63. Khi nào chọn anonymous class?

Chọn anonymous class khi:

- Một implementation nhỏ, đặc thù cho một điểm gọi.
- Cần **extends một class** và override behavior ngay tại chỗ.
- Interface có **nhiều abstract methods**, không thể dùng lambda đơn giản.
- Callback cần fields/helpers hoặc instance initializer nhỏ.
- Muốn hide implementation class name và chỉ expose contract.
- Test cần stub/fake interface implementation ngắn.

### Khi nào không nên?

- Implementation dài, khó review/debug; dùng named local/member/top-level class.
- Behavior được tái sử dụng ở nhiều sites; tránh copy-paste anonymous bodies.
- Chỉ có một functional method rất ngắn; lambda thường rõ hơn.
- Cần explicit constructor validation/complex object lifecycle.
- Cần public API expose methods không nằm trong base type.
- Cần serialization/persistence/versioned type names ổn định.
- Cần framework DI/reflection mapping/class discovery hoạt động theo named concrete type.

## 64. Decision table

| Nhu cầu | Phương án thường phù hợp |
| --- | --- |
| Runnable in một dòng | Lambda |
| Interface hai abstract methods, logic ngắn | Anonymous class |
| Override abstract base class method tại một call site | Anonymous subclass |
| Custom instance state nhỏ trong callback | Anonymous class hoặc named local class |
| Reuse một implementation nhiều nơi | Named class |
| Helper không cần outer state và dùng nhiều methods | Static nested class |
| Trả object qua public interface, hide implementation | Anonymous/local named class |
| Framework cần named class/constructor contract ổn định | Named class |
| Captured state lớn và long-lived listener | Thiết kế ownership/cleanup trước khi chọn syntax |
| Base type `final` hoặc sealed không cho phép extension | Composition/permitted implementation |

Syntax không thay thế thiết kế contract. Nếu một behavior phải mở rộng lâu dài, đặt tên cho class và trách nhiệm thường giúp bảo trì hơn.

## 65. Những hiểu nhầm phổ biến

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “`new Interface() { ... }` tạo trực tiếp interface object.” | Tạo anonymous implementation class instance. |
| “Anonymous class không có runtime Class object.” | Vẫn có Class metadata. |
| “Mọi anonymous instances đều cùng class.” | Chỉ cùng declaration/site phù hợp; khác sites có khác anonymous types. |
| “`new Base() { ... }` không phải kế thừa.” | Anonymous subclass extends Base. |
| “Chỉ abstract class mới được anonymous extends.” | Concrete non-final class cũng được. |
| “Có thể anonymous extends final class.” | Final cấm subclassing. |
| “Sealed types tự cho anonymous subclass.” | Phải theo permits restrictions. |
| “Anonymous class có thể bỏ required abstract methods.” | Concrete anonymous class phải implement đầy đủ. |
| “Anonymous class có explicit named constructor.” | Không có tên class để khai báo constructor. |
| “Superclass constructor không chạy.” | Có, theo constructor invocation semantics. |
| “Anonymous helper method luôn gọi được qua interface variable.” | Declared supertype giới hạn members. |
| “`this` trong anonymous class là outer object.” | This là anonymous instance. |
| “`super` gọi outer method.” | Super thuộc superclass of anonymous class. |
| “Anonymous class trong static method có Outer.this.” | Static context không có outer instance. |
| “Captured local không cần effectively final.” | Bắt buộc final/effectively final. |
| “Captured mutable List trở thành immutable.” | Không; chỉ local reference không bị reassign. |
| “Lambda và anonymous class có this giống nhau.” | Lambda dùng lexical this; anonymous dùng own instance this. |
| “Interface nhiều abstract methods luôn viết lambda được.” | Lambda cần functional interface. |
| “Có thể viết `new A(), B() { ... }`.” | Không có cú pháp multiple direct supertypes như thế. |
| “Diamond syntax với anonymous class không được Java 17 hỗ trợ.” | Hỗ trợ từ Java 9 với restrictions. |
| “`@Override` không cần vì code ngắn.” | Rất nên dùng để compiler kiểm tra contract. |
| “Callback anonymous object tự được GC sau method return.” | Registry/captured refs có thể giữ reachable. |
| “Không cần lưu callback reference để unregister.” | Nhiều APIs cần đúng listener instance. |
| “Effectively final đảm bảo thread safety.” | Không; synchronization riêng. |
| “Anonymous class cho phép thêm checked exceptions tùy ý.” | Override throws contract vẫn áp dụng. |

## 66. Bài tập 1 — Implements interface

~~~java
Runnable r = new Runnable() {
    @Override
    public void run() {
        System.out.println("A");
    }
};
r.run();
~~~

**Đáp án:** In `A`. Expression tạo anonymous implementation of Runnable rồi gọi method run.

## 67. Bài tập 2 — Extends abstract class

~~~java
abstract class Animal {
    abstract String sound();
}

Animal a = new Animal() {
    @Override
    String sound() {
        return "meow";
    }
};
~~~

**Câu hỏi:** Có tạo Animal abstract object trực tiếp không?

**Đáp án:** Không. Có một concrete anonymous subclass extends Animal, và `a.sound()` trả `meow`.

## 68. Bài tập 3 — Extends concrete class

~~~java
class Greeting {
    String text() { return "Hello"; }
}

Greeting g = new Greeting() {
    @Override
    String text() { return "Hi"; }
};
~~~

**Đáp án:** `g.text()` trả `Hi` do dynamic dispatch. Anonymous class extends concrete Greeting dù Greeting không abstract.

## 69. Bài tập 4 — Hai `new` ở hai source sites

~~~java
Runnable a = new Runnable() { public void run() {} };
Runnable b = new Runnable() { public void run() {} };
~~~

**Đáp án:** `a == b` false, và `a.getClass() == b.getClass()` false vì đây là hai declarations ở hai source locations.

## 70. Bài tập 5 — Cùng factory site

Một method `create()` trả `new Runnable() { ... }` tại một source location. Gọi twice `create()` thì identity và runtime class so sánh ra sao?

**Đáp án:** Hai returned objects thường khác identity, nhưng cùng anonymous runtime class trong same defining-loader context. Captured values có thể khác nhau.

## 71. Bài tập 6 — Method chỉ có trong anonymous class

~~~java
Runnable r = new Runnable() {
    public void run() {}
    public void extra() {}
};
// r.extra();
~~~

**Đáp án:** Bỏ comment `r.extra()` sẽ lỗi compile vì declared type Runnable không có extra(). Muốn expose extra, thay contract interface hoặc dùng named type thích hợp.

## 72. Bài tập 7 — Reassign captured local

~~~java
int counter = 0;
counter++;

Runnable r = new Runnable() {
    public void run() {
        // System.out.println(counter);
    }
};
~~~

**Đáp án:** Nếu bỏ comment, compiler từ chối capture counter vì counter không effectively final. Muốn counter per-callback mutable, dùng instance field trong anonymous class.

## 73. Bài tập 8 — Anonymous `this` và lambda `this`

Trong instance method, anonymous class method in `this.getClass().isAnonymousClass()`; lambda body in `this.getClass().getSimpleName()`.

**Đáp án:** Anonymous `this` là anonymous object; lambda `this` là enclosing instance của lexical context. Chúng không tương đương.

## 74. Bài tập 9 — Superclass constructor

~~~java
abstract class Job {
    Job(String id) {}
    abstract void execute();
}

// new Job() {
//     void execute() {}
// };
~~~

**Đáp án:** Nếu uncomment, compiler báo không có compatible no-arg constructor. Phải viết `new Job("X") { @Override void execute() {} }` (với access hợp lệ).

## 75. Bài tập 10 — Chọn lambda hay anonymous?

Một interface chỉ có `void run()` và behavior là in một dòng: lambda hay anonymous class?

**Đáp án:** Lambda thường ngắn, rõ. Nếu cần anonymous class identity/instance fields, hoặc nhiều abstract methods, anonymous class có thể phù hợp hơn.

## 76. Bài tập 11 — Sealed type

Một `sealed interface Result permits Success, Failure`. Có được `new Result() { ... }` trực tiếp không?

**Đáp án:** Không, vì anonymous class không thuộc danh sách permitted direct implementations. Dùng permitted concrete class hoặc thiết kế extension point khác theo sealed type model.

## 77. Bài tập 12 — Callback lifecycle

Bạn đăng ký anonymous listener vào EventBus rồi muốn unregister nhưng không lưu reference. Rủi ro?

**Đáp án:** Không có reference tới đúng instance đã đăng ký; tạo một anonymous listener mới cùng code không phải cùng object, có thể không remove đúng listener. Lưu handle/reference và unregister theo contract của EventBus.

## 78. Checklist kiểm tra nhanh

- [ ] Tôi phân biệt new Interface() { ... } và new Base(args) { ... }.
- [ ] Tôi biết anonymous class là class thật, không có source simple name.
- [ ] Tôi biết implements interface khác extends concrete/abstract class.
- [ ] Tôi biết dynamic dispatch đến anonymous override.
- [ ] Tôi biết abstract methods phải implement đầy đủ.
- [ ] Tôi biết methods implement interface phải public.
- [ ] Tôi dùng `@Override` cho interface/superclass methods.
- [ ] Tôi biết superclass constructors chạy và nhận args ở new expression.
- [ ] Tôi biết anonymous class không có named constructor.
- [ ] Tôi dùng instance initializer khi thực sự cần, không để lộ partial this.
- [ ] Tôi biết anonymous fields/helpers không tự accessible qua declared supertype.
- [ ] Tôi hiểu local `var` có thể infer anonymous type trong Java 17.
- [ ] Tôi biết `this` là anonymous object, `Outer.this` là owner khi hợp lệ.
- [ ] Tôi biết `super` chỉ đến superclass behavior.
- [ ] Tôi biết captured local/parameter phải final hoặc effectively final.
- [ ] Tôi phân biệt captured primitive snapshot với mutable object reference.
- [ ] Tôi biết lambda có khác biệt về this/capture và functional-interface requirement.
- [ ] Tôi biết anonymous class có thể extend concrete non-final class.
- [ ] Tôi biết không extend final class hoặc direct implement sealed type bị cấm.
- [ ] Tôi biết một anonymous expression chỉ nêu một direct supertype.
- [ ] Tôi biết generic interfaces và diamond syntax trong Java 17.
- [ ] Tôi không làm public API phụ thuộc generated anonymous class name.
- [ ] Tôi dùng reflection `isAnonymousClass()` thay vì parse tên.
- [ ] Tôi biết cùng source expression có thể tạo nhiều objects cùng runtime class.
- [ ] Tôi biết hai source anonymous class expressions khác nhau có runtime types khác nhau.
- [ ] Tôi biết captured state/callback registry có thể kéo dài owner lifetime.
- [ ] Tôi giữ đúng callback reference để unsubscribe.
- [ ] Tôi biết effectively final không làm shared mutable state thread-safe.
- [ ] Tôi tuân thủ checked exceptions/visibility/access contracts.
- [ ] Tôi chọn named class khi behavior lớn hoặc cần reuse/versioning.
- [ ] Tôi có thể dự đoán stdout và compile errors trong các ví dụ.

**Kết luận:** Lớp vô danh là công cụ Java định nghĩa **một subclass hoặc một interface implementation không tên ngay tại expression tạo object**. `new Interface() { ... }` dùng để implements interface; `new Base(args) { ... }` dùng để extends class và gọi superclass constructor phù hợp. Object của anonymous class vẫn có identity, runtime Class và dynamic dispatch như các objects khác. Anonymous class rất phù hợp cho customization nhỏ/callback cục bộ, nhưng không thay thế được contract/interface design, constructor safety, capture rules, lifecycle management hoặc thread safety. Với một functional callback ngắn, cân nhắc lambda; với behavior dài và tái sử dụng, cân nhắc named class.
