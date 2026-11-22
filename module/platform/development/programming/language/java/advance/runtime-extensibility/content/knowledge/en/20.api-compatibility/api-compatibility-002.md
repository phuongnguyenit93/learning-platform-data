# Tác động khi thêm, xóa hoặc đổi chữ ký phương thức của interface

## 1. Vì sao thay đổi interface gây sự cố với plugin cũ?

Trong ứng dụng có khả năng mở rộng lúc chạy, host và plugin thường được biên dịch, phát hành và triển khai vào những thời điểm khác nhau. Một thư viện công bố interface cho bên thứ ba implements, sau đó thư viện thay đổi API. JVM không tự biên dịch lại plugin JAR đã phát hành; nó thực thi file .class và tham chiếu phương thức đã được ghi trong bytecode.

Giả sử API v1 công bố:

~~~java
package demo.spi;

public interface Handler {
    String execute();
}
~~~

Plugin được biên dịch với API v1:

~~~java
package demo.impl;

import demo.spi.Handler;

public final class LegacyHandler implements Handler {
    @Override
    public String execute() {
        return "legacy";
    }
}
~~~

Sau đó API v2 thêm một phương thức bắt buộc:

~~~java
package demo.spi;

public interface Handler {
    String execute();
    String version();
}
~~~

Recompile source của LegacyHandler với API v2 sẽ gặp lỗi vì class chưa triển khai version(). Tuy nhiên **LegacyHandler.class v1** có thể vẫn nạp được và gọi execute(). Chỉ khi host mới gọi version() trên object cũ, JVM mới không tìm thấy một implementation cụ thể và có thể ném **AbstractMethodError**.

**Câu hỏi phải đặt ra không chỉ là “API mới compile được không?”, mà là “source cũ, binary cũ và hành vi khi chạy còn phù hợp không?”** Đây là trọng tâm của tương thích API Java.

## 2. Ba lớp tương thích phải phân biệt

| Loại | Câu hỏi | Kiểm thử |
|---|---|---|
| **Source compatibility** | Source client/implementer cũ có biên dịch lại với interface mới không? | Recompile old source + API v2 |
| **Binary compatibility** | Client.class và plugin.class cũ có tiếp tục liên kết với interface mới mà không rebuild? | Giữ old binaries, thay API runtime |
| **Behavioral compatibility** | Method vẫn làm đúng chức năng, trả giá trị và lỗi theo hợp đồng cũ không? | Contract/integration tests với nhiều phiên bản |

Theo **Java Language Specification (JLS) Chapter 13**, binary compatibility chú trọng các binary đã có từ trước tiếp tục link được. Một thay đổi có thể được JLS đánh giá **binary-compatible** trong khi việc recompile source cũ thất bại hoặc lời gọi mới trên old instance phát sinh lỗi.

Ví dụ về những khác biệt:

- Thêm abstract method có thể giữ binary compatibility nhưng phá source compatibility của concrete implementer cũ.
- Thêm default method có thể giữ việc gọi method mới nhưng làm thay đổi semantics hoặc gây default conflict.
- Thêm overload giữ lời gọi bytecode cũ, nhưng code cũ khi recompile có thể chọn overload mới.
- Đổi return type có thể nhìn “hợp lý” trong Java source nhưng làm thay JVM descriptor.

Với SPI/ServiceLoader/URLClassLoader, càng phải kiểm tra **old plugin JAR + new host API**, vì plugin có thể do người khác phát hành và không nằm trong mã nguồn của bạn.

## 3. Chữ ký Java source và JVM descriptor không đồng nhất

Trong Java source, phương thức được phân biệt theo method signature (tên và các kiểu tham số theo quy tắc JLS); **return type một mình không đủ để overload**:

~~~java
// Không hợp lệ: hai khai báo cùng Java signature.
interface Wrong {
    String get();
    Object get();
}
~~~

Ở class file, **JVM method descriptor** chứa **parameter descriptors và return descriptor**. Đây là các ví dụ:

| Java method | JVM descriptor |
|---|---|
| **void reset()** | **()V** |
| **String execute()** | **()Ljava/lang/String;** |
| **Object execute()** | **()Ljava/lang/Object;** |
| **void save(int n)** | **(I)V** |
| **void save(long n)** | **(J)V** |
| **String find(String id)** | **(Ljava/lang/String;)Ljava/lang/String;** |
| **void send(String... names)** | **([Ljava/lang/String;)V** |

**V** biểu diễn void, **I** là int, **J** là long, **L...;** biểu diễn kiểu reference và **[** là mảng. Tên class trong descriptor dùng dấu gạch chéo giữa các phần package.

Vì descriptor bao gồm return type, hai interface có các method:

~~~java
// V1:
String execute();

// V2:
Object execute();
~~~

không có cùng descriptor, dù Java source của method có cùng tên và danh sách tham số. Old caller.class có thể vẫn tham chiếu **execute:()Ljava/lang/String;**; nó không tự đổi sang **execute:()Ljava/lang/Object;** khi JVM nạp API mới. Covariant return trong một số tình huống overriding có thể khiến compiler tạo bridge, nhưng **không thể mặc định dựa vào bridge để giữ ABI của một interface bị sửa declaration**.

Tương tự, đổi **save(int)** sang **save(long)** làm descriptor đổi từ **(I)V** sang **(J)V**. Java compiler có thể widen int thành long trong một lời gọi source mới, nhưng old .class không thực hiện lại overload resolution.

**Lệnh kiểm tra descriptor của một API:**

~~~bash
javap -classpath api.jar -s -p demo.spi.Handler
~~~

Lệnh **javap -c -p** giúp inspect instruction của old caller, đặc biệt **invokeinterface**, và xác nhận symbol mà client đã biên dịch.

## 4. Ma trận ảnh hưởng của các thay đổi interface

| Thay đổi | Recompile source cũ | Old binaries | Rủi ro runtime |
|---|---|---|---|
| **Thêm abstract method** | Concrete implementer thiếu method thường báo lỗi | Theo JLS vẫn binary-compatible | New caller gọi old object: **AbstractMethodError** |
| **Thêm default method** | Thường không cần implement; có thể clash | Binary-compatible theo quy tắc JLS | Xung đột defaults: **IncompatibleClassChangeError**; behavior đổi |
| **Thêm static/private method** | Không tạo thêm obligation instance | Binary-compatible | Source naming/overload hoặc logic nội bộ có thể chịu ảnh hưởng |
| **Thêm overload khác tham số** | Có thể đổi overload resolution hoặc ambiguous | Old caller tiếp tục gọi descriptor đã chọn | Behavior giữa old/rebuilt caller khác |
| **Xóa method** | Old client dùng method không compile | Có thể binary-incompatible | **NoSuchMethodError** nếu symbol không còn được resolve |
| **Đổi tên method** | Client và implementer cần cập nhật | Giống xóa tên cũ + thêm tên mới | **NoSuchMethodError** |
| **Đổi số lượng/kiểu tham số** | Có thể phải sửa lời gọi | Descriptor cũ biến mất nếu không giữ overload | **NoSuchMethodError** |
| **Đổi return type có erasure khác** | Có thể phải cập nhật cả caller và provider | Return descriptor thay đổi | **NoSuchMethodError** hoặc lỗi dispatch |
| **Đổi throws clause** | Caller có thể cần đổi catch/throws | Không đổi descriptor | Behavior/checked exception contract đổi |
| **Đổi generic arguments cùng erasure** | Có thể mất type compatibility | Thường giữ descriptor | Lỗi cast/semantics có thể xuất hiện |
| **Đổi default thành abstract** | Old implementation có thể thiếu body | Không phải tiến hóa an toàn ở mức invocation | Có thể **AbstractMethodError** |

Bảng là quy tắc định hướng, **không phải lời hứa rằng mọi tình huống đều ném đúng một loại error**. Ví dụ xóa method khỏi một interface cụ thể nhưng còn declaration phù hợp ở superinterface có thể vẫn resolve được. Khi chẩn đoán phải kiểm tra hierarchy và bytecode runtime thực tế.

## 5. Thêm abstract method: link được không có nghĩa gọi được

API v1 chỉ có **execute()**; API v2 có thêm **String version()** abstract. Hai phép thử có kết quả khác nhau:

**A. Recompile LegacyHandler.java cùng API v2.** Java compiler yêu cầu concrete class phải cung cấp implementation cho version(). Đây là sự cố **source compatibility**.

**B. Không recompile LegacyHandler.class v1; chạy với API v2.** Theo JLS §13.5.4, thêm abstract interface method không tự phá binary compatibility của pre-existing binaries. Plugin class cũ có thể được nạp và gọi execute().

Tuy nhiên, new host biên dịch với API v2 khi gọi **Handler.version()** trên LegacyHandler v1 sẽ không tìm được implementation phù hợp, và có thể ném **AbstractMethodError**. Lỗi xuất hiện ở **invocation**, không nhất thiết ở class load.

~~~text
Handler v1: execute()
       |
       +---- LegacyHandler v1: implements execute()
                         |
                         +---- Handler v2: execute(), version()
                                            |
                                            +-- execute() -> OK
                                            +-- version() -> AbstractMethodError
~~~

Vì vậy, nếu interface là **SPI bên thứ ba tự implement**, không nên bổ sung abstract method rồi mặc định tất cả plugin cũ có khả năng thực hiện nó. Dùng **default method đúng ngữ nghĩa**, **capability interface** hoặc chính sách bắt nâng cấp plugin.

## 6. Thêm default method: thường an toàn hơn nhưng không tuyệt đối

Default method có implementation trong interface:

~~~java
public interface Handler {
    String execute();

    default String version() {
        return "unknown";
    }
}
~~~

Old plugin có thể kế thừa version() mặc định. Nhưng có các điều kiện quan trọng:

1. **Hành vi fallback phải hợp lệ.** "unknown" không được coi là version xác thực nếu host cần version chính xác.
2. **Class method có thể thắng interface default.** Method trên class hoặc superclass được chọn theo dispatch rules tương ứng.
3. **Xung đột nhiều defaults.** Một class cũ implements hai interfaces độc lập; khi cả hai sau đó thêm default cùng chữ ký, JVM có thể ném **IncompatibleClassChangeError** lúc gọi.
4. **Đổi implementation của default** thay đổi behavior dù descriptor không đổi.
5. **Một method trùng tên đã tồn tại trong class** có thể bất ngờ được xem là override của method interface mới, gây semantics ngoài dự kiến.

Ví dụ khái niệm:

~~~java
interface Left {
    default String label() { return "left"; }
}

interface Right { }

final class Both implements Left, Right { }
~~~

Nếu Right phiên bản mới cũng cung cấp **default String label()**, một Both.class đã biên dịch với Right cũ có thể gặp conflict khi JVM chọn method. JLS §13.5.7 mô tả tình huống gây **IncompatibleClassChangeError**; build source lại có thể báo lỗi compile trước khi đến runtime. Hai loại lỗi không mâu thuẫn vì một bên là source mới, bên kia là binary cũ.

**Quy tắc thực tế:** Default method hữu ích để mở rộng ABI nhưng không thay thế bài toán hợp đồng nghiệp vụ và việc kiểm thử mọi plugin đã phát hành.

## 7. Thêm static, private method hoặc overload

Một interface Java 17 có thể có static method và private helper:

~~~java
public interface Handler {
    String execute();

    static String normalize(String s) {
        return s == null ? "" : s.strip();
    }

    private static String fallback() {
        return "none";
    }

    default String display() {
        String text = normalize(execute());
        return text.isEmpty() ? fallback() : text;
    }
}
~~~

Thêm static hoặc private method **không buộc plugin implement thêm một instance abstract method**, và JLS xem đây là thay đổi binary-compatible. Nhưng **display()** là default method mới nên vẫn phải cân nhắc conflict và behavior như phần 6.

Thêm overload có một loại rủi ro khác:

~~~java
// V1:
interface Format {
    String apply(Object value);
}

// V2 thêm overload:
interface Format {
    String apply(Object value);
    String apply(String value);
}
~~~

Old caller đã compile **apply("hello")** khi chỉ có **apply(Object)**. Binary cũ vẫn tham chiếu descriptor của apply(Object). Nếu recompile client với API v2, Java compiler có thể chọn apply(String), và hai version chạy khác behavior. Thêm overload **apply(Integer)** cùng apply(String) còn có thể khiến **apply(null)** trở thành ambiguous khi compile lại.

**Overload resolution xảy ra tại compile-time**, không chạy lại mỗi khi một API JAR được thay.

## 8. Xóa method: tác động lên old caller.class

Giả sử v1 có:

~~~java
public interface Handler {
    String execute();
}
~~~

V3 xóa execute():

~~~java
public interface Handler {
    // Không còn execute().
}
~~~

Một old client.class đã chứa symbolic reference đến **demo/spi/Handler.execute:()Ljava/lang/String;**. Nếu runtime interface/hierarchy không còn method khớp, reference đó không được resolve, nên JVM có thể ném **NoSuchMethodError**.

Điểm dễ nhầm là **LegacyHandler.class cũ vẫn định nghĩa execute()**. Điều ấy không tự cứu được lời gọi **invokeinterface Handler.execute** của old client: JVM phải resolve method declaration ở interface trước rồi mới xét implementation.

**Phân biệt hai lỗi:**

- **NoSuchMethodError:** symbolic method reference không còn resolve được với tên/descriptor ở API runtime.
- **AbstractMethodError:** method declaration có thể resolve nhưng không có method implementation cụ thể phù hợp cho receiver object.

Không xóa một method public chỉ vì source host hiện tại không còn gọi. Old client/plugin JAR ở ngoài repository vẫn có thể tham chiếu binary entry point ấy.

## 9. Đổi tên, tham số, return type là rủi ro ABI

### Đổi tên method

~~~java
// V1:
String execute();

// V2:
String run();
~~~

Nếu xóa execute() mà chỉ để run(), old caller không tự chuyển tên. Cách mở rộng tương thích:

~~~java
interface Handler {
    String execute();

    default String run() {
        return execute();
    }
}
~~~

Vẫn cần kiểm tra default behavior và xung đột. Nếu hai tên không cùng ngữ nghĩa, nên tạo capability mới thay vì adapter giả.

### Đổi tham số

~~~java
// V1:
void publish(String text);

// V2:
void publish(String text, boolean urgent);
~~~

JVM descriptor cũ và mới khác nhau. Nếu muốn giữ old client:

~~~java
interface Publisher {
    void publish(String text);

    default void publish(String text, boolean urgent) {
        publish(text);
    }
}
~~~

Nhưng default bỏ qua urgent; **nếu urgent mang ý nghĩa bắt buộc**, giải pháp trên có thể sai về nghiệp vụ. Một interface **UrgentPublisher** mới sẽ minh bạch hơn.

### Đổi kiểu trả về

~~~java
// V1:
String execute();

// V2:
Object execute();
~~~

Dù String là subtype của Object, descriptor thay đổi. Java source không thể khai báo hai method cùng tên và tham số chỉ khác return type. Muốn giữ đường cũ, thêm một **tên khác**:

~~~java
interface Handler {
    String execute();

    default Object executeValue() {
        return execute();
    }
}
~~~

Trong một số trường hợp compiler có thể sinh **bridge method** để duy trì polymorphism do generics hoặc covariant overriding. Không suy diễn rằng mọi interface ABI được đổi return type đều nhận bridge đúng; hãy kiểm tra bằng **javap -v** và thử old client.class. Tương tự, đổi **void refresh()** thành **boolean refresh()** làm descriptor **()V** đổi thành **()Z**.

## 10. Những thay đổi không nhất thiết đổi descriptor

### Generics và type erasure

~~~java
// V1:
void accept(java.util.List<String> values);

// V2:
void accept(java.util.List<Integer> values);
~~~

Thông thường cả hai cùng erased descriptor **(Ljava/util/List;)V**. Tuy vậy source code có thể không tương thích, logic xử lý phần tử khác đi, và runtime có thể gặp ClassCastException. Ngược lại đổi **List<String>** thành **Collection<String>** sẽ làm erasure khác, do đó đổi descriptor.

Đổi **first bound** của type variable cũng có thể thay đổi erasure ngay cả khi các tên generic vẫn giống nhau.

### Throws clause

~~~java
// V1:
String read() throws java.io.IOException;

// V2:
String read() throws java.sql.SQLException;
~~~

Checked throws không nằm trong JVM method descriptor. Đổi throws thường không phá binary linkage nhưng có thể phá source compatibility khi caller recompile do xử lý checked exceptions khác. Semantics của loại lỗi phát sinh trong runtime cũng cần được xét.

### Varargs

~~~java
// V1:
void send(String[] values);

// V2:
void send(String... values);
~~~

Cả hai cùng JVM descriptor **([Ljava/lang/String;)V**. Tuy vậy cú pháp gọi được compiler chấp nhận khi recompile có thể khác, chẳng hạn cho phép truyền nhiều String arguments riêng lẻ.

### Parameter names

Đổi tên tham số **left, right** thành **a, b** không đổi descriptor. Nhưng một framework dựa vào reflection parameter metadata, annotations hoặc data binding vẫn có thể thấy tác động ở tầng behavior.

## 11. Ví dụ Java 17: một plugin.class cũ với ba API runtime

Mục tiêu bài thực hành là **không biên dịch lại plugin.class cũ**. Ta build các phiên bản Handler.class trong những thư mục riêng, lần lượt chạy với old/new callers. Cả ví dụ dùng Java 17+ và không cần thư viện ngoài.

### 11.1. Cây thư mục

~~~text
interface-evolution-demo/
├── src/
│   ├── v1/
│   │   ├── api/demo/spi/Handler.java
│   │   ├── impl/demo/impl/LegacyHandler.java
│   │   └── client/demo/client/OldClient.java
│   ├── v2/
│   │   ├── api/demo/spi/Handler.java
│   │   └── client/demo/client/NewClient.java
│   ├── v2-default/api/demo/spi/Handler.java
│   └── v3/api/demo/spi/Handler.java
└── build/     # tạo bằng các lệnh biên dịch
~~~

### 11.2. API v1 và plugin v1

**src/v1/api/demo/spi/Handler.java**

~~~java
package demo.spi;

public interface Handler {
    String execute();
}
~~~

**src/v1/impl/demo/impl/LegacyHandler.java**

~~~java
package demo.impl;

import demo.spi.Handler;

public final class LegacyHandler implements Handler {
    @Override
    public String execute() {
        return "legacy";
    }
}
~~~

**src/v1/client/demo/client/OldClient.java**

~~~java
package demo.client;

import demo.spi.Handler;
import demo.impl.LegacyHandler;

public final class OldClient {
    public static void main(String[] args) {
        Handler handler = new LegacyHandler();
        try {
            System.out.println("removed=" + handler.execute());
        } catch (NoSuchMethodError error) {
            System.out.println("removed=NoSuchMethodError");
        }
    }
}
~~~

OldClient được compile với API v1; nó có method reference cũ đến Handler.execute(). Trong ví dụ chỉ bắt Error để chứng minh failure mode, không phải cách xử lý production được khuyến nghị.

### 11.3. API v2 abstract và new caller

**src/v2/api/demo/spi/Handler.java**

~~~java
package demo.spi;

public interface Handler {
    String execute();
    String version();
}
~~~

**src/v2/client/demo/client/NewClient.java**

~~~java
package demo.client;

import demo.spi.Handler;
import demo.impl.LegacyHandler;

public final class NewClient {
    public static void main(String[] args) {
        Handler handler = new LegacyHandler();
        System.out.println("execute=" + handler.execute());

        try {
            System.out.println("version=" + handler.version());
        } catch (AbstractMethodError error) {
            System.out.println("version=AbstractMethodError");
        }
    }
}
~~~

### 11.4. API v2 có default version()

**src/v2-default/api/demo/spi/Handler.java**

~~~java
package demo.spi;

public interface Handler {
    String execute();

    default String version() {
        return "v2-default";
    }
}
~~~

Đây là interface thay thế cho API v2 abstract, giữ nguyên **version:()Ljava/lang/String;** nhưng có body. Ta sẽ dùng cùng NewClient.class và LegacyHandler.class để so kết quả.

### 11.5. API v3 xóa execute()

**src/v3/api/demo/spi/Handler.java**

~~~java
package demo.spi;

public interface Handler {
    // Không còn execute().
}
~~~

Không có superinterface cung cấp declaration execute(), nên method reference của OldClient v1 không còn nơi resolve.

### 11.6. Compile trên Linux/macOS

Chạy từ root **interface-evolution-demo**:

~~~bash
mkdir -p build/v1-api build/impl build/old-client
mkdir -p build/v2-api build/new-client build/v2-default-api build/v3-api

javac --release 17 -encoding UTF-8 \
  -d build/v1-api src/v1/api/demo/spi/Handler.java

javac --release 17 -encoding UTF-8 \
  -cp build/v1-api -d build/impl \
  src/v1/impl/demo/impl/LegacyHandler.java

javac --release 17 -encoding UTF-8 \
  -cp build/v1-api:build/impl -d build/old-client \
  src/v1/client/demo/client/OldClient.java

javac --release 17 -encoding UTF-8 \
  -d build/v2-api src/v2/api/demo/spi/Handler.java

javac --release 17 -encoding UTF-8 \
  -cp build/v2-api:build/impl -d build/new-client \
  src/v2/client/demo/client/NewClient.java

javac --release 17 -encoding UTF-8 \
  -d build/v2-default-api \
  src/v2-default/api/demo/spi/Handler.java

javac --release 17 -encoding UTF-8 \
  -d build/v3-api src/v3/api/demo/spi/Handler.java
~~~

Lưu ý thứ tự: build/impl và build/old-client được tạo từ API v1. Sau đó **không recompile** hai artifact đó. NewClient được compile với API v2 nhưng sử dụng LegacyHandler.class đã biên dịch từ v1.

### 11.7. Compile trên Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force build/v1-api, build/impl, build/old-client, build/v2-api, build/new-client, build/v2-default-api, build/v3-api | Out-Null

javac --release 17 -encoding UTF-8 -d build/v1-api src/v1/api/demo/spi/Handler.java

javac --release 17 -encoding UTF-8 -cp build/v1-api -d build/impl src/v1/impl/demo/impl/LegacyHandler.java

javac --release 17 -encoding UTF-8 -cp "build/v1-api;build/impl" -d build/old-client src/v1/client/demo/client/OldClient.java

javac --release 17 -encoding UTF-8 -d build/v2-api src/v2/api/demo/spi/Handler.java

javac --release 17 -encoding UTF-8 -cp "build/v2-api;build/impl" -d build/new-client src/v2/client/demo/client/NewClient.java

javac --release 17 -encoding UTF-8 -d build/v2-default-api src/v2-default/api/demo/spi/Handler.java

javac --release 17 -encoding UTF-8 -d build/v3-api src/v3/api/demo/spi/Handler.java
~~~

**Classpath separator** là **:** trên Linux/macOS và **;** trên Windows. Với các lệnh chạy, luôn đưa **đúng một** thư mục có demo/spi/Handler.class vào classpath. Đặt nhiều phiên bản API cùng tên trên classpath có thể dẫn tới nạp bản ngoài dự kiến.

### 11.8. Case A: thêm abstract method

Linux/macOS:

~~~bash
java -cp build/v2-api:build/impl:build/new-client demo.client.NewClient
~~~

Windows:

~~~powershell
java -cp "build/v2-api;build/impl;build/new-client" demo.client.NewClient
~~~

**Stdout:**

~~~text
execute=legacy
version=AbstractMethodError
~~~

LegacyHandler.class vẫn execute() được. Version declaration ở Handler v2 tồn tại, nhưng old class không implement được version(), dẫn đến AbstractMethodError khi new caller invoke.

### 11.9. Case B: thêm default method

Linux/macOS:

~~~bash
java -cp build/v2-default-api:build/impl:build/new-client demo.client.NewClient
~~~

Windows:

~~~powershell
java -cp "build/v2-default-api;build/impl;build/new-client" demo.client.NewClient
~~~

**Stdout:**

~~~text
execute=legacy
version=v2-default
~~~

NewClient.class và LegacyHandler.class được giữ nguyên. Runtime interface dùng default version() nên Java có implementation thích hợp để dispatch.

### 11.10. Case C: xóa method

Linux/macOS:

~~~bash
java -cp build/v3-api:build/impl:build/old-client demo.client.OldClient
~~~

Windows:

~~~powershell
java -cp "build/v3-api;build/impl;build/old-client" demo.client.OldClient
~~~

**Stdout:**

~~~text
removed=NoSuchMethodError
~~~

OldClient.class được compile khi Handler.execute() còn tồn tại. Handler v3 không còn method declaration phù hợp, nên old invokeinterface reference không thể resolve. Việc LegacyHandler.class có execute() không thay thế declaration đã bị xóa khỏi interface.

### 11.11. Kiểm tra class files bằng javap

~~~bash
javap -classpath build/v1-api -s demo.spi.Handler
javap -classpath build/v2-api -s demo.spi.Handler
javap -classpath build/v2-default-api -s demo.spi.Handler
javap -classpath build/v3-api -s demo.spi.Handler
javap -classpath build/old-client -c demo.client.OldClient
~~~

Bạn sẽ thấy execute() trong v1/v2/v2-default, version() trong v2/v2-default và không còn execute() trong v3. OldClient.class vẫn tham chiếu Handler.execute() như khi biên dịch lần đầu.

## 12. Các lỗi JVM cần phân biệt

| Error | Lý do thường gặp | Cách debug |
|---|---|---|
| **AbstractMethodError** | Method declaration tồn tại nhưng receiver không có implementation cụ thể | Kiểm tra old implementer và method dispatch |
| **NoSuchMethodError** | Symbolic method reference name/descriptor không được resolve | So javap caller v1 và interface v2 |
| **IncompatibleClassChangeError** | Invocation kind/hierarchy/default conflict không tương thích | Kiểm tra instance vs static, class/interface hierarchy |
| **IllegalAccessError** | Visibility/module access của method/type đổi | Kiểm tra public/export/encapsulation |
| **VerifyError** | Bytecode/hierarchy sau thay đổi không hợp lệ đối với verification | Kiểm tra classfile và quan hệ superinterface |

**AbstractMethodError** và **NoSuchMethodError** là subclass của **IncompatibleClassChangeError**. Chúng là LinkageError, không phải checked business exceptions.

**NoSuchMethodException** của reflection là một ngoại lệ khác với **NoSuchMethodError** khi JVM giải quyết lời gọi đã được biên dịch.

Lỗi binary evolution có thể phát sinh muộn tại lần đầu JVM resolve/invoke method; ứng dụng khởi động được chưa chứng minh mọi plugin/API đã tương thích.

## 13. Phương án tiến hóa an toàn cho thư viện công khai

**Giữ method cũ và thêm adapter method:**

~~~java
interface Handler {
    String execute();

    default String run() {
        return execute();
    }
}
~~~

Cách này giúp caller cũ và plugin cũ có entry point cũ, trong khi client mới dùng run() nếu semantics tương đương.

**Tách interface cho capability mới:**

~~~java
interface Handler {
    String execute();
}

interface VersionedHandler extends Handler {
    String version();
}
~~~

Host:

~~~java
// Mảnh minh họa: handler có sẵn từ plugin host.
if (handler instanceof VersionedHandler versioned) {
    System.out.println(versioned.version());
} else {
    System.out.println("Legacy plugin: version capability unavailable");
}
~~~

Old plugin tiếp tục implements Handler; new plugin có thể implements VersionedHandler. Host biết khi nào có capability mà không tự suy đoán.

**Deprecate trước khi remove:**

~~~java
interface Handler {
    @Deprecated(since = "2.0", forRemoval = false)
    String execute();

    default String run() {
        return execute();
    }
}
~~~

Annotation **@Deprecated** là tín hiệu migration, không tự sửa ABI. Giữ entry point cũ nếu cần support old binaries. Chỉ xóa sau một migration policy và release/version boundary rõ.

**Versioning contract khi thay đổi không thể thích ứng:** Tách interface HandlerV1 và HandlerV2 hoặc xuất bản adapter riêng, thay vì thay đổi descriptor của cùng một method name rồi giả định old plugin vẫn tương thích.

**Đừng dùng fallback sai nghiệp vụ:** Một default **pay(amount, currency)** chỉ gọi **pay(amount)** và bỏ qua currency có thể sai trong giao dịch đa tiền tệ. An toàn kiểu/binary không bù được lỗi nghiệp vụ; dùng capability interface hoặc yêu cầu nâng cấp plugin nếu feature mới bắt buộc.

## 14. Ma trận kiểm thử trước khi phát hành

| Build/run | Để xác nhận |
|---|---|
| Recompile old plugin source với new API | Source compatibility của implementer |
| Recompile old client source với new API | Source compatibility của caller, overload ambiguity |
| Old plugin.class + new API | Binary/link compatibility và method implementation |
| Old client.class + new API | Old symbolic references còn hợp lệ hay không |
| New client.class + old plugin.class + new API | Default/capability/AbstractMethodError |
| Plugin implements nhiều interfaces | Default conflict và dispatch |
| So method descriptors ở API v1/v2 | ABI thay đổi cụ thể |
| Contract/integration tests | Behavioral compatibility |

Trong runtime extensibility, phải **giữ nguyên artifact old .class/JAR**, không clean rebuild toàn bộ rồi kết luận old binary vẫn tương thích. Chỉ chạy trên runtime có **đúng phiên bản API** mà bạn muốn kiểm thử; hai copy interface cùng tên từ hai classloaders còn có thể gây vấn đề class identity khác với chữ ký method.

## 15. Sai lầm và câu hỏi tự kiểm tra

**Sai lầm: “Thêm abstract method là binary-compatible nên chắc chắn an toàn.”** Sai ở mức invocation: old implementer không tự có body mới.

**Sai lầm: “Thêm default method luôn không gây lỗi.”** Default conflict và thay đổi semantics vẫn có thể xảy ra.

**Sai lầm: “Đổi return String sang Object chỉ là nới kiểu.”** JVM descriptor thay đổi; old caller vẫn tham chiếu descriptor cũ.

**Sai lầm: “Đổi int thành long được Java tự widen lúc chạy.”** Compiler source mới có thể widen, nhưng old binary không tự chọn lại method.

**Sai lầm: “Class cũ vẫn có execute() nên có thể xóa execute() khỏi interface.”** Old invokeinterface reference phải resolve ở interface/hierarchy runtime.

**Sai lầm: “Đổi List<String> thành List<Integer> không có rủi ro do erasure.”** Erasure có thể giữ descriptor nhưng source contract và runtime type safety vẫn thay đổi.

**Câu 1.** Thêm **abstract flush()** vào interface khiến old plugin.class có thể link không? Host v2 gọi flush() sẽ ra sao?

**Đáp án:** JLS cho phép old binary tiếp tục link khi thêm abstract interface member, nhưng nếu không có implementation trên old class, lời gọi có thể ném AbstractMethodError.

**Câu 2.** Vì sao xóa method ở interface gây NoSuchMethodError dù class implementer có method trùng tên?

**Đáp án:** Old binary dùng symbolic reference đến interface method. Nếu method không còn được resolve đúng descriptor trong interface/hierarchy, JVM không thể dùng reference ấy.

**Câu 3.** Thêm overload apply(String) có làm old bytecode gọi apply(Object) đổi sang String không?

**Đáp án:** Không. Overload đã được compiler chọn và ghi descriptor khi biên dịch. Recompile source có thể chọn overload mới.

**Câu 4.** Checked throws khác có đổi descriptor không?

**Đáp án:** Không. Nhưng có thể phá source compatibility và thay đổi contract exception.

**Câu 5.** Có thể dùng default method để giả lập mọi capability mới không?

**Đáp án:** Không. Default phải có semantics hợp lệ và không gây conflict; khi capability bắt buộc và old plugin không có, dùng interface mở rộng/version mới hoặc nâng cấp plugin.

## 16. Checklist trước khi sửa một interface công khai

1. Phân loại thay đổi: thêm abstract/default/static/private/overload hay xóa/đổi descriptor.
2. So JVM descriptors bằng **javap -s**, chú ý return type, erasure và bridge.
3. Recompile old source để kiểm tra source compatibility.
4. Chạy old caller.class và old plugin.class **không recompile** với API runtime mới.
5. Kiểm tra AbstractMethodError khi new caller gọi abstract method trên old plugin.
6. Kiểm tra NoSuchMethodError khi old caller tham chiếu method đã xóa/đổi.
7. Kiểm tra xung đột default và semantics của fallback.
8. Xem checked throws, generics và framework reflection dù descriptor không đổi.
9. Ưu tiên adapter/default đúng nghĩa, capability interface, deprecation và migration policy.
10. Lưu JAR cũ làm test fixture và công bố rõ version compatibility của host và plugin.

**Kết luận:** Thêm abstract method vào interface không nhất thiết phá binary link nhưng có thể gây **AbstractMethodError** khi gọi trên implementation cũ. Thêm default method thường hỗ trợ tiến hóa hợp đồng nhưng có rủi ro **IncompatibleClassChangeError** và đổi behavior. Xóa hoặc đổi method name, parameter hay return descriptor có thể dẫn đến **NoSuchMethodError** ở caller.class cũ. Để phát hành API ổn định, hãy kiểm tra **source, binary và behavior** bằng cả old binaries, không chỉ build thành công phiên bản mới.

### Tài liệu chuẩn Java 17

- Java Language Specification, Chapter 13, Binary Compatibility, đặc biệt §13.2, §13.5.4 và §13.5.7: https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html
- JVM Specification, Method Descriptors §4.3.3: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3.3
- JVMS, Interface Method Resolution §5.4.3.4: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.4
- JVMS, invokeinterface §6.5: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.invokeinterface
- Java SE 17 AbstractMethodError: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AbstractMethodError.html
- Java SE 17 NoSuchMethodError: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoSuchMethodError.html
