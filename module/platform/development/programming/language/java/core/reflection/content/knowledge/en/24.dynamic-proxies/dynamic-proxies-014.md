# Dynamic proxy qua interface và proxy bằng lớp con sinh bytecode trong Java

Trong Java Reflection, hai kỹ thuật thường được gọi chung là **proxy** vì cùng đặt một lớp trung gian trước hành vi thật để ghi log, kiểm tra quyền, đo thời gian, giao dịch hoặc gọi từ xa. Tuy nhiên, **JDK dynamic proxy** và **proxy dựa trên lớp con (subclass proxy)** có cấu trúc kiểu, cách chặn lời gọi và giới hạn hoàn toàn khác nhau.

Điểm dễ nhầm nhất: **JDK dynamic proxy cũng tạo ra bytecode/lớp ở runtime**. Sự khác biệt chính không phải “một bên sinh bytecode, một bên không”, mà là **lớp proxy được sinh ra implements các interface** hay **extends một lớp cụ thể và ghi đè các method có thể override**.

## 1. Hai cơ chế ở cấp độ kiểu và lời gọi

### JDK dynamic proxy: đứng trước interface

Cho interface `Greeting` và implementation `GreetingImpl`:

```text
Client giữ tham chiếu Greeting
          |
          v
Đối tượng proxy (lớp JVM tạo, extends java.lang.reflect.Proxy)
          | implements Greeting
          v
Phương thức giao diện trên proxy
          |
          v
InvocationHandler.invoke(proxy, method, args)
          |
          +--> gọi GreetingImpl thật, hoặc thực hiện hành vi khác
```

Khi gọi `greeting.say("An")`, lời gọi đi vào method do lớp proxy tạo rồi chuyển đến `InvocationHandler`. Handler **có thể** ủy quyền đến một target, trả kết quả giả lập, gọi qua mạng hoặc ném exception. JDK Proxy không bắt buộc có một target instance.

Ví dụ khởi tạo:

```java
Greeting proxy = (Greeting) Proxy.newProxyInstance(
        Greeting.class.getClassLoader(),
        new Class<?>[] {Greeting.class},
        handler);
```

Đây là **đoạn minh họa**: giả sử `Greeting` và `handler` đã được định nghĩa. Đối tượng trả về thỏa `proxy instanceof Greeting`, nhưng thông thường **không phải** instance của `GreetingImpl` dù handler đang chuyển lời gọi đến `GreetingImpl`. Lớp proxy kế thừa `java.lang.reflect.Proxy`, không kế thừa implementation `GreetingImpl`. Một lớp JDK proxy có thể implements nhiều interface hợp lệ.

### Subclass proxy: đứng trước một lớp cụ thể

Với lớp `Service` có method `work()` có thể ghi đè:

```text
Client giữ tham chiếu Service
          |
          v
Đối tượng thuộc lớp con do thư viện sinh ra
          | extends Service
          v
Method work() được override trong lớp con
          |
          +--> interceptor trước lời gọi
          +--> gọi super.work() / chuyển đến target (tùy cơ chế)
          +--> interceptor sau lời gọi
```

Các thư viện như **Byte Buddy** hoặc **CGLIB** có thể tạo bytecode và định nghĩa một lớp con ở runtime, từ đó ghi đè method hợp lệ để cài logic trung gian. Đối tượng này có thể dùng như chính lớp cơ sở: `subclassProxy instanceof Service` là `true`. Không cần `Service` khai báo interface.

**Chú ý:** một thư viện sinh bytecode có thể hỗ trợ nhiều kiểu tạo lớp khác nhau; ở đây “subclass proxy” chỉ cơ chế cụ thể là sinh lớp `extends Service` và override method. Cách gọi target, lưu state và tạo instance tùy framework/cấu hình.

## 2. JDK Proxy chuyển lời gọi qua InvocationHandler như thế nào?

API trọng tâm nằm trong `java.lang.reflect.Proxy` và `java.lang.reflect.InvocationHandler`:

- `Proxy.newProxyInstance(loader, interfaces, handler)`: tạo instance của một lớp proxy hỗ trợ các interface được yêu cầu. Interface phải thỏa ràng buộc visibility, class loader và module của JVM.
- `InvocationHandler.invoke(Object proxy, Method method, Object[] args)`: nhận proxy đang được gọi, metadata `Method` và đối số. Với method không tham số, `args` có thể là `null`.
- `method.invoke(target, args)`: một cách **tùy chọn** để ủy quyền vào implementation; khi method thật ném exception, Reflection có thể bọc trong `InvocationTargetException`, cần xử lý cause.
- `Proxy.isProxyClass(type)` và `Proxy.getInvocationHandler(proxy)`: giúp kiểm tra lớp JDK proxy và truy xuất handler khi thích hợp.

Không phải lời gọi Java nào trên đối tượng proxy cũng vào handler. Các interface instance method sẽ được chuyển qua handler; `equals(Object)`, `hashCode()` và `toString()` khai báo từ `Object` cũng được chuyển đến handler. Ngược lại, `getClass()` là method `final` của `Object` và không bị handler chặn. Static method của interface không được gọi bằng dispatch của instance proxy.

**Default method của interface:** invocation qua proxy vẫn được chuyển tới handler; handler phải quyết định xử lý, chẳng hạn ủy quyền cho target có implementation hoặc dùng `InvocationHandler.invokeDefault(...)` (Java 16+), nếu phù hợp. Đừng mặc định mọi default method sẽ tự chạy mà không qua handler.

**Kiểu của proxy:** caller nên giữ proxy bằng biến interface. Nếu cố cast proxy JDK sang lớp implementation cụ thể, có thể gặp `ClassCastException`. Method chỉ có ở implementation và **không nằm trong interface được proxy implements** cũng không thể gọi qua API interface đó.

## 3. Subclass proxy chặn lời gọi bằng override như thế nào?

Một subclass proxy có thể được hình dung bằng mã nguồn do người viết tự tạo sau; thư viện thật sinh cấu trúc tương đương bằng bytecode thay vì cần viết sẵn lớp này:

```java
class Service {
    String work() {
        return "done";
    }
}

class ServiceProxyLike extends Service {
    @Override
    String work() {
        System.out.println("before");
        String result = super.work();
        System.out.println("after");
        return result;
    }
}
```

Đây là **đoạn minh họa cấu trúc**, không phải bằng chứng rằng thư viện nào cũng gọi `super.work()`. Một số proxy gọi method gốc trên chính instance lớp con, trong khi proxy của framework khác có thể chuyển tiếp đến target instance riêng hoặc dùng interceptor chain. Cấu trúc bytecode và đường đi thực tế phải kiểm tra theo framework đang dùng.

Giới hạn cốt lõi xuất phát từ luật kế thừa/override của Java:

- **`final class`** không thể được subclass. Record mặc nhiên là `final`; sealed class cũng hạn chế danh sách lớp được phép kế thừa.
- **`final instance method`** không thể bị override. Một subclass proxy thuần túy không thể chèn interceptor thông qua override của method ấy.
- **`private method`** không được override; **`static method`** được resolve theo lớp, không tham gia virtual dispatch/override. Constructor cũng không phải method được override.
- Method `public`/`protected` và method package-private có thể override **khi các quy tắc truy cập và package cho phép**. Module encapsulation, class loader và cách định nghĩa lớp có thể đặt thêm giới hạn.
- Việc tạo instance cần một chiến lược hợp lệ: constructor có thể được gọi hoặc framework có thể dùng kỹ thuật instantiation riêng. Vì vậy **không được suy ra** từ chữ “subclass proxy” rằng constructor target chạy đúng một lần theo một cách cố định.

Một method `final` vẫn có thể được **gọi** trên subclass instance nếu được kế thừa và truy cập hợp lệ; điều thiếu là điểm override để chèn logic. Kết quả thực tế còn phụ thuộc cách framework quản lý state và target.

## 4. So sánh trực diện

| Tiêu chí | JDK dynamic proxy | Proxy là lớp con sinh bytecode |
|---|---|---|
| Kiểu proxy | Lớp sinh ra extends `Proxy`, implements interface | Lớp sinh ra extends lớp đích |
| Điều kiện chính | Cần một hoặc nhiều interface phù hợp | Cần lớp đích có thể kế thừa và method có thể override |
| `instanceof` | Đúng với interface được proxy implements | Đúng với lớp cơ sở |
| Điểm chặn | Method trong lớp proxy chuyển tới `InvocationHandler.invoke` | Override method đi qua interceptor/logic trong lớp con |
| Method chỉ có ở concrete class | Không trở thành API của proxy nếu không nằm trên interface | Có thể chặn nếu được kế thừa và override hợp lệ |
| Method `final` của concrete class | Không áp dụng để chọn method qua interface; không proxy concrete class | Không thể chặn bằng override |
| `private`/`static` method của target | Không được gọi qua interface instance dispatch | Không thể override/chặn bằng override |
| Multiple interfaces | Có thể implements nhiều interface | Lớp con chỉ có một superclass nhưng có thể implements interface |
| Target instance thật | Không bắt buộc; handler quyết định | Phụ thuộc framework: có thể gọi `super` hoặc target riêng |
| Cách tạo proxy | API JDK sẵn có | Thường dùng thư viện như Byte Buddy/CGLIB |
| Kiểu sử dụng thích hợp | Contract dựa trên interface | Cần duy trì kiểu concrete class hoặc class không có interface |

Cả hai đều chịu quy tắc về type identity, class loader, module và visibility của JVM. Cả hai cũng có chi phí runtime nhất định; không nên khẳng định cơ chế nào **luôn** nhanh hơn nếu chưa đo với workload và framework thực tế.

## 5. Chương trình Java 17+ minh họa cả hai đường đi

Ví dụ sau chạy chỉ với JDK. Phần JDK Proxy dùng proxy thật; phần lớp con được **viết tay để mô phỏng chính xác ý tưởng override**, tránh yêu cầu tải thêm thư viện Byte Buddy/CGLIB. Ví dụ không giả vờ rằng lớp viết tay là bytecode do thư viện tự sinh.

Lưu thành **`ProxyVsSubclassDemo.java`**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class ProxyVsSubclassDemo {
    interface Greeting {
        String say(String name);
    }

    static class GreetingImpl implements Greeting {
        @Override
        public String say(String name) {
            return "Hello, " + name;
        }

        public String extra() {
            return "Only available on concrete class";
        }
    }

    static class Service {
        String work() {
            return "work done";
        }

        final String fixed() {
            return "fixed";
        }
    }

    // Minh họa cấu trúc lớp mà thư viện sinh bytecode có thể tạo.
    static class ServiceSubclassDemo extends Service {
        @Override
        String work() {
            System.out.println("[subclass] before");
            String result = super.work();
            System.out.println("[subclass] after");
            return result;
        }
    }

    public static void main(String[] args) {
        GreetingImpl target = new GreetingImpl();

        Greeting interfaceProxy = (Greeting) Proxy.newProxyInstance(
                Greeting.class.getClassLoader(),
                new Class<?>[] {Greeting.class},
                (proxy, method, arguments) -> {
                    System.out.println("[interface] " + method.getName());
                    try {
                        return method.invoke(target, arguments);
                    } catch (InvocationTargetException e) {
                        throw e.getCause();
                    }
                });

        System.out.println(interfaceProxy.say("An"));
        System.out.println("proxy instanceof Greeting = "
                + (interfaceProxy instanceof Greeting));
        System.out.println("proxy instanceof GreetingImpl = "
                + (interfaceProxy instanceof GreetingImpl));
        System.out.println("proxy superclass is Proxy = "
                + (interfaceProxy.getClass().getSuperclass() == Proxy.class));

        Service subclassProxy = new ServiceSubclassDemo();
        System.out.println(subclassProxy.work());
        System.out.println(subclassProxy.fixed());
        System.out.println("subclass instanceof Service = "
                + (subclassProxy instanceof Service));
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 -encoding UTF-8 ProxyVsSubclassDemo.java
java ProxyVsSubclassDemo
```

**Stdout:**

```text
[interface] say
Hello, An
proxy instanceof Greeting = true
proxy instanceof GreetingImpl = false
proxy superclass is Proxy = true
[subclass] before
[subclass] after
work done
fixed
subclass instanceof Service = true
```

**Giải thích kết quả:**

1. Khi gọi `interfaceProxy.say("An")`, method của lớp proxy JDK gọi handler. Handler in `[interface] say`, rồi dùng Reflection gọi `GreetingImpl.say`.
2. Proxy implements `Greeting` nhưng không extends `GreetingImpl`; do đó hai dòng `instanceof` lần lượt là `true` và `false`. Superclass trực tiếp là `Proxy`.
3. `ServiceSubclassDemo` là một lớp con của `Service`. Method `work()` được override, in log trước/sau và gọi `super.work()`; đây là **cơ chế override** mà thư viện sinh subclass có thể tạo tự động.
4. `fixed()` là `final` và không được override trong `ServiceSubclassDemo`. Nó vẫn trả `fixed`, không đi qua log `[subclass]`.
5. `subclassProxy` vẫn là `Service` theo `instanceof` và có thể được truyền vào chỗ nhận `Service`, khác với JDK interface proxy khi code cần concrete type `GreetingImpl`.

Lưu ý: trong handler, `method.invoke(target, arguments)` có thể gây `InvocationTargetException`; ví dụ đã bóc cause để giữ exception thật của method. Nếu thay `target` bằng chính `proxy` rồi gọi lại cùng method, handler có thể gọi đệ quy vô hạn.

## 6. Những khác biệt có tác động khi dùng framework

### Không có interface, hoặc caller cần concrete type

Nếu API nhận `Service` như concrete class và cần thay đối tượng bằng proxy vẫn là `Service`, một JDK proxy chỉ implements `ServiceInterface` (nếu có) thường không thể cast thành `Service`. Proxy theo subclass có thể phù hợp **nếu** `Service` cho phép kế thừa và có các method cần chặn có thể override.

Ngược lại, nếu API đã thống nhất dựa trên interface, JDK proxy cung cấp hợp đồng rõ ràng và dùng trực tiếp API chuẩn của Java. Một implementation với method bổ sung ngoài interface sẽ không tự được thêm vào contract proxy.

### Self-invocation không thể kết luận chỉ từ chữ “proxy”

Hãy phân biệt **virtual dispatch của Java** với **cách framework gọi target**:

- Nếu một instance của lớp con thực sự gọi method được override thông qua `this.work()`, Java có thể dispatch vào override của lớp con.
- Nếu một framework đặt proxy bên ngoài một **target instance riêng**, lời gọi nội bộ `this.work()` trên target có thể đi thẳng vào target và **bỏ qua proxy**.
- Vì vậy với Spring AOP hay các framework tương tự, cần xem **thiết kế proxy, chuỗi interceptor và đối tượng nào thực thi lời gọi**, chứ không mặc định subclass proxy sẽ xử lý mọi self-invocation.

### Lỗi và giới hạn thường gặp

| Hiện tượng | Cách giải thích hoặc kiểm tra |
|---|---|
| `ClassCastException` khi cast JDK proxy sang implementation | Proxy chỉ nhận danh tính qua interface được implements, không kế thừa implementation |
| Không chặn được method `final` | Subclass không thể override; cân nhắc interface proxy, đổi API/method hoặc một kỹ thuật instrumentation khác nếu được thiết kế |
| Không tạo được subclass | Kiểm tra class `final`/record/sealed, constructor phù hợp, quyền truy cập, package và module |
| JDK proxy gặp method có checked exception | Nếu handler ném checked exception ngoài danh sách `throws` được method giao diện cho phép, caller có thể nhận `UndeclaredThrowableException` |
| Handler bất ngờ chạy khi log proxy | `toString()` và các method `Object` nói trên có thể đi vào handler; cẩn thận vòng lặp đệ quy |
| Không nhìn thấy method concrete-only qua JDK proxy | Thêm hành vi vào interface nếu đó thật sự là phần contract cần công khai |
| Tên lớp proxy hoặc hành vi khác giữa môi trường | Không phụ thuộc tên lớp sinh ra; kiểm tra version JVM/thư viện, class loader và module configuration |

Không nên dùng tên dạng `$Proxy...` hoặc tên lớp con được generator sinh làm định danh ổn định. Chúng là chi tiết triển khai. Dùng interface/class contract cùng API metadata phù hợp để nhận diện.

## 7. Chọn cơ chế nào?

- **Ưu tiên JDK dynamic proxy** khi lớp đích đã có interface phù hợp, ứng dụng gọi qua interface, và muốn một lớp trung gian cho log, quyền truy cập, đo đạc hay remote invocation bằng thư viện chuẩn.
- **Xem xét subclass proxy** khi caller cần đúng kiểu concrete class hoặc lớp đích không có interface, đồng thời các method cần chặn có thể override, lớp có thể được kế thừa và môi trường cho phép tạo/định nghĩa lớp.
- **Kiểm tra framework thực tế** khi làm việc với Spring AOP, Hibernate hoặc mocking library: một framework có thể lựa chọn chiến lược proxy theo cấu hình và trường hợp sử dụng; việc dùng Byte Buddy/CGLIB không tự chứng minh mọi method được chặn hay mọi constructor chạy theo cùng một đường.

Đặt yêu cầu trước khi lựa chọn: **caller đang dùng interface hay class? Method cần chặn có thể override không? Proxy có target riêng hay chính là instance thực thi?** Ba câu trả lời này thường xác định hướng phù hợp.

## 8. Tự kiểm tra

**Câu 1.** JDK dynamic proxy có sinh bytecode không?

**Có.** Nó tạo lớp proxy ở runtime; khác biệt là lớp ấy extends `Proxy` và implements interface, không extends implementation concrete.

**Câu 2.** Có thể cast JDK proxy của `Greeting` thành `GreetingImpl` chỉ vì handler chuyển tiếp đến `GreetingImpl` không?

**Không.** Việc handler gọi một target không làm thay đổi quan hệ kế thừa của proxy object.

**Câu 3.** Nếu `Service` là `final class`, thư viện có thể dùng cơ chế subclass proxy thông thường không?

**Không.** Java cấm kế thừa final class. Có thể cần thiết kế dựa trên interface hoặc một kỹ thuật khác với subclassing.

**Câu 4.** Một method `final` có thể chạy trên subclass instance không? Có bị chặn qua override không?

**Có thể chạy nếu được kế thừa và truy cập hợp lệ**, nhưng **không thể chặn bằng override** trong lớp con.

**Câu 5.** Vì sao việc gọi `this.someMethod()` đôi khi bypass interceptor dù framework dùng class-based proxy?

Vì framework có thể thực thi method trên **target instance riêng** hoặc có quy tắc interception riêng; phải phân tích nơi diễn ra dispatch, không suy từ hình thức lớp proxy.

## Tài liệu tham khảo chuẩn

- Java SE 17 API: [`java.lang.reflect.Proxy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html).
- Java SE 17 API: [`java.lang.reflect.InvocationHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html).
- Java Language Specification §8.4.8 (override), §8.1.1.2 (final class), §15.12 (method invocation).
- Tài liệu Byte Buddy và CGLIB của đúng phiên bản đang sử dụng khi cần xác minh chiến lược tạo lớp, interceptor và instantiation.

**Ghi nhớ:** JDK Proxy dùng một lớp implements interface để chuyển lời gọi tới `InvocationHandler`; subclass proxy dùng một lớp extends concrete class, thường chặn hành vi qua override. Cả hai có thể sinh bytecode ở runtime, nhưng **hình dạng kiểu và điểm chặn lời gọi khác nhau**, nên khả năng cast, phạm vi method và giới hạn `final` cũng khác nhau.
