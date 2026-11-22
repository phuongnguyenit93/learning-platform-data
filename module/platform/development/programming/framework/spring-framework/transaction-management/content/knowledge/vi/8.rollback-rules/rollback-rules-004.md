# Rủi ro khớp quá rộng của rollbackForClassName và noRollbackForClassName

> **Spring Framework — Transaction Management → Quy tắc rollback.** Bài học giải thích vì sao hai thuộc tính `rollbackForClassName` và `noRollbackForClassName` trong `@Transactional` có thể ảnh hưởng đến **những exception không hề được chủ ý cấu hình**, từ đó khiến transaction rollback hoặc commit ngoài mong đợi. Trọng tâm là cơ chế so khớp **chuỗi con trong tên lớp exception**, các trường hợp trùng tên và nested class, cách Spring giải quyết nhiều rule, cùng cách lựa chọn rule an toàn và kiểm thử được.

## 1. Vấn đề: một tên exception có thể khớp nhiều kiểu khác nhau

Xét một dịch vụ lưu đơn hàng. Nếu xảy ra lỗi nghiệp vụ `OrderRejectedException`, người viết muốn ghi nhận trạng thái đã xử lý, nên cấu hình ngoại lệ đó **không làm rollback**:

```java
@Transactional(noRollbackForClassName = "OrderRejectedException")
public void submitOrder() {
    // Lưu dữ liệu và xử lý nghiệp vụ...
}
```

Đây là **fragment**: phương thức phải nằm trong Spring bean được quản lý giao dịch, không phải chương trình Java độc lập. Vấn đề xuất hiện khi codebase bổ sung `OrderRejectedExceptionCritical`, một `RuntimeException` biểu thị lỗi nghiêm trọng: **tên lớp này vẫn chứa chuỗi `OrderRejectedException`**.

Với `noRollbackForClassName = "OrderRejectedException"`, Spring có thể chọn **không rollback** ngay cả khi method ném `OrderRejectedExceptionCritical`. Đối với `RuntimeException`, điều đó đi ngược chính sách rollback mặc định thông thường. Nếu có thao tác ghi thành công trước lỗi, transaction manager có thể yêu cầu commit các thay đổi đó.

Chiều ngược lại cũng đáng chú ý:

```java
@Transactional(rollbackForClassName = "OrderRejectedException")
public void submitOrder() {
    // ...
}
```

Người viết có thể chỉ định rollback cho một checked exception cụ thể, nhưng `OrderRejectedExceptionV2` (một lớp **không kế thừa** `OrderRejectedException`) cũng có thể bị buộc rollback nếu tên chứa chuỗi đó. Thậm chí exception lồng tên `OrderRejectedException$Details` cũng có thể khớp.

**Tên giống nhau không nói lên quan hệ kế thừa.** String pattern matching không thay thế được Java type checking. Đây là rủi ro cốt lõi cần nhớ khi sử dụng hậu tố `ClassName`.

## 2. Phân biệt bốn thuộc tính rollback của `@Transactional`

Import đúng annotation là `org.springframework.transaction.annotation.Transactional`. Có bốn nhóm cấu hình:

| Thuộc tính | Kiểu giá trị | Điều kiện so khớp | Ý nghĩa khi khớp |
| --- | --- | --- | --- |
| `rollbackFor` | `Class<? extends Throwable>[]` | Exception thực tế bằng hoặc **kế thừa** kiểu đã khai báo | Chọn rollback |
| `noRollbackFor` | `Class<? extends Throwable>[]` | Exception thực tế bằng hoặc **kế thừa** kiểu đã khai báo | Chọn không rollback |
| `rollbackForClassName` | `String[]` | Tên exception trong chuỗi kế thừa **chứa** pattern | Chọn rollback |
| `noRollbackForClassName` | `String[]` | Tên exception trong chuỗi kế thừa **chứa** pattern | Chọn không rollback |

Hai thuộc tính dựa vào `Class` được Spring **khuyến nghị sử dụng** vì tương thích với Java type system. Hai thuộc tính `ClassName` dựa trên chuỗi, thường hữu ích khi không thể tham chiếu trực tiếp đến lớp exception tại thời điểm biên dịch, nhưng cần kiểm soát pattern đặc biệt cẩn thận.

Ví dụ hai cách định nghĩa rollback:

```java
@Transactional(rollbackFor = OrderRejectedException.class)
public void typedRule() {
    // Match OrderRejectedException và các subclass thật sự của nó.
}

@Transactional(rollbackForClassName = "OrderRejectedException")
public void stringRule() {
    // Match mọi Throwable có tên lớp/superclass chứa chuỗi trên.
}
```

Đoạn này là **fragment**, giả định có lớp `OrderRejectedException` và các phương thức trong Spring bean. Một đoạn `ClassName` không phải regex, glob hoặc tên class phải được tìm chính xác; Spring không yêu cầu pattern phải trùng toàn bộ tên lớp.

### Quy tắc mặc định khi không có custom rule khớp

Theo mặc định tiêu chuẩn của Spring transaction attributes, `RuntimeException` và `Error` gây rollback, còn checked `Exception` thường không gây rollback. Nếu cấu hình một custom rule nhưng nó **không khớp** exception đang xét, Spring sử dụng default policy tương ứng.

Từ Spring Framework 6.2, ứng dụng có thể thay đổi chính sách mặc định ở mức cấu hình (ví dụ `@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)`), nên kết quả khi **không có rule khớp** có thể khác mặc định truyền thống. Các rule cụ thể trên annotation vẫn cần được xét theo cơ chế ưu tiên.

**Quan trọng:** `rollbackForClassName` và `noRollbackForClassName` chỉ đưa ra quyết định rollback/commit theo rule ở transaction boundary. Chúng không bảo đảm database thực sự commit được nếu driver, engine hoặc transaction đã ở trạng thái rollback-only; cũng không tự biến việc nuốt exception thành rollback.

## 3. Spring so khớp chuỗi tên exception như thế nào?

Về bản chất, Spring dùng logic của `RollbackRuleAttribute` và `NoRollbackRuleAttribute`. Với rule tạo bằng một `String`, Spring kiểm tra tên class exception **có chứa** pattern hay không. Quy trình xét class hiện tại rồi superclass chain có thể diễn đạt bằng mô hình sau:

```text
exception được ném ra
       |
       v
kiểm tra tên class của exception
       |
       +-- chứa pattern? ---> match tại depth = 0
       |
       +-- không chứa -----> kiểm tra superclass
                              |
                              +-- chứa pattern? ---> depth = 1
                              |
                              +-- tiếp tục lên superclass...
                              |
                              +-- không còn superclass khớp => depth = -1
```

Đây là **mô hình giải thích**, không phải đoạn mã Spring sao chép nguyên văn.

Các chi tiết có ý nghĩa thực tế:

1. Pattern là **chuỗi con** (`String.contains(...)`), có phân biệt chữ hoa/chữ thường theo tên class Java.
2. Không hỗ trợ ký hiệu wildcard/regex trong pattern rollback này. `"Order*Exception"` **không** có nghĩa “mọi lớp có tiền tố Order và hậu tố Exception”.
3. Spring có thể xét **tên lớp đầy đủ** (`fully qualified class name`) lẫn tên superclass; pattern `"OrderRejectedException"` có thể khớp `com.acme.orders.OrderRejectedException`, `com.other.OrderRejectedException` hoặc `com.acme.OrderRejectedExceptionV2`.
4. Với lớp lồng nhau, binary class name của Java chứa ký tự `$`; ví dụ `com.acme.OrderRejectedException$Details` có chứa `com.acme.OrderRejectedException`.
5. Rule so khớp theo **kiểu exception được ném và superclass của nó**. Đừng lẫn việc đi lên superclass với việc tự động đi qua `Throwable.getCause()`: một rule dựa trên tên cause **không tự** được áp dụng khi exception wrapper mới là exception thoát khỏi method.
6. Nếu rule khớp một superclass, kết quả depth dương. Khi nhiều rule cùng match, depth là yếu tố quyết định rule thắng.

Một hệ quả hơi bất ngờ: một **fully qualified pattern** vẫn là chuỗi con chứ không phải quy tắc bằng tuyệt đối.

```java
@Transactional(
    rollbackForClassName = "com.acme.orders.OrderRejectedException"
)
public void submitOrder() {
    // ...
}
```

Cấu hình trên vẫn có thể khớp `com.acme.orders.OrderRejectedExceptionV2` và `com.acme.orders.OrderRejectedException$Details`. Ghi package name giảm khả năng va chạm giữa các package nhưng **không loại bỏ** va chạm hậu tố/lớp lồng nhau.

## 4. Bốn kiểu trùng khớp ngoài ý muốn

### 4.1. Pattern quá chung: `"Exception"`

```java
@Transactional(rollbackForClassName = "Exception")
public void process() {
    // ...
}
```

Pattern `"Exception"` xuất hiện trong tên rất nhiều lớp như `IOException`, `SQLException`, `IllegalArgumentException` và `RuntimeException`. Nó có thể khớp ở depth 0 và chi phối cả những rule khác vốn chỉ khớp qua superclass.

Nếu thật sự muốn chính sách rollback cho mọi `Exception` (bao gồm checked exceptions), **type rule** `rollbackFor = Exception.class` là lựa chọn rõ ràng và type-safe; hoặc dùng cấu hình default rollback phù hợp với phiên bản Spring khi đó là một chính sách toàn cục.

Tuy nhiên, `"Exception"` không phải một pattern khớp mọi `Throwable`: `Error` là nhánh khác của `Throwable`, không phải subclass của `Exception`. Đừng viết tài liệu rằng `rollbackForClassName = "Exception"` là “rollback trên tất cả lỗi” mà không nói rõ giới hạn này.

### 4.2. Pattern tên ngắn khớp lớp trùng tên ở package khác

```java
@Transactional(noRollbackForClassName = "ValidationException")
public void register() {
    // ...
}
```

`com.acme.customer.ValidationException` và `com.vendor.gateway.ValidationException` có thể có mục đích hoàn toàn khác, nhưng đều chứa `ValidationException`. Nếu lớp thứ hai biểu thị lỗi hạ tầng cần rollback, cấu hình trên vẫn có thể yêu cầu không rollback.

Việc một dependency mới thêm exception cùng tên có thể **lặng lẽ thay đổi semantics giao dịch** mà file chứa `@Transactional` không được sửa.

### 4.3. Cùng tiền tố, thêm hậu tố: `CustomExceptionV2`

Giả sử có các lớp **ngang hàng, không có quan hệ kế thừa**:

```java
class PaymentDeclinedException extends Exception {}

class PaymentDeclinedExceptionV2 extends Exception {}
```

Một rule chuỗi:

```java
@Transactional(
    rollbackForClassName = "PaymentDeclinedException"
)
public void settle() {
    // ...
}
```

Khớp **cả hai lớp** mặc dù người viết có thể chỉ muốn lớp thứ nhất. Trái lại:

```java
@Transactional(
    rollbackFor = PaymentDeclinedException.class
)
public void settle() {
    // ...
}
```

Chỉ khớp `PaymentDeclinedException` hoặc **subclass thực sự** của nó, không khớp `PaymentDeclinedExceptionV2` nếu đây là sibling class.

Tên `V2`, `Special`, `Critical`, `Retryable`, `Impl` hoặc tên do codegen thêm có thể làm pattern cũ khớp quá rộng. Tên lớp chứa pattern chứ không phải subclass theo Java là trọng tâm rủi ro.

### 4.4. Lớp lồng nhau: ký tự `$` trong binary name

```java
class CustomException extends Exception {
    static class AuditDetail extends Exception {}
}
```

Tên binary thường có dạng:

```text
com.acme.CustomException
com.acme.CustomException$AuditDetail
```

Rule `rollbackForClassName = "com.acme.CustomException"` **vẫn khớp** `CustomException$AuditDetail` dù `AuditDetail` không kế thừa `CustomException`. Nó chỉ được khai báo bên trong `CustomException` và tên binary có chuỗi tên lớp ngoài.

Điều này khác hẳn type-based rule `rollbackFor = CustomException.class`, vốn chỉ match quan hệ kế thừa thực sự.

## 5. Vì sao `noRollbackForClassName` đặc biệt nguy hiểm?

Với `rollbackForClassName` quá rộng, Spring có thể **hủy** một transaction mà người viết dự định commit. Với `noRollbackForClassName` quá rộng, Spring có thể **yêu cầu commit** một transaction sau khi đã có lỗi nghiêm trọng — đôi khi tệ hơn vì các thao tác trước lỗi có thể được ghi nhận không đầy đủ.

Ví dụ:

```java
@Transactional(noRollbackForClassName = "BusinessException")
public void transfer() {
    jdbc.update("UPDATE accounts SET balance = balance - 50 WHERE id = 1");
    // Các thao tác phía sau có thể thất bại.
    checkAndCreditDestination();
}
```

Đoạn trên là **fragment minh họa**, không phải chương trình độc lập; cần cấu hình JDBC, bảng dữ liệu và hàm `checkAndCreditDestination()`. Giả sử hàm sau ném `BusinessExceptionCritical extends RuntimeException`. Vì tên chứa `BusinessException`, một rule “no rollback” quá rộng có thể ngăn áp dụng hành vi rollback mặc định cho runtime exception. Manager có thể cố commit phần trừ tiền đã thực thi nếu database chưa tự làm transaction rollback-only.

Điều này không có nghĩa Spring luôn có thể commit: một số lỗi SQL có thể khiến database đặt transaction vào trạng thái không thể commit, hoặc một inner transaction có thể đã đánh dấu rollback-only. **Quy tắc `noRollbackForClassName` xác định lựa chọn theo exception, không ghi đè khả năng của database.**

So sánh hai cấu hình:

```java
// Dễ khớp ngoài ý muốn.
@Transactional(noRollbackForClassName = "BusinessException")
public void riskyMethod() { /* ... */ }

// Rõ ràng hơn: chỉ class này và subclasses thật sự được miễn rollback.
@Transactional(noRollbackFor = BusinessException.class)
public void saferMethod() { /* ... */ }
```

Trong code thực tế, `BusinessException` cần có định nghĩa và ý nghĩa nghiệp vụ rõ. Không nên chọn `noRollbackFor` chỉ để tránh exception bị hiển thị: quyết định giữ hay hoàn tác thay đổi phải theo **bất biến dữ liệu**. Một exception nghiệp vụ vẫn có thể đòi rollback; ví dụ thao tác chuyển tiền không hợp lệ phải trả số dư về trạng thái trước đó.

### Pattern `"Exception"` trong `noRollbackForClassName`

```java
@Transactional(noRollbackForClassName = "Exception")
public void dangerous() { /* ... */ }
```

Điều này có thể miễn rollback cho **rất nhiều RuntimeException**, bao gồm `IllegalStateException`, `IllegalArgumentException`, `NullPointerException` và `DataAccessException` thông thường. Nó gần như đảo chính sách rollback mặc định đối với nhánh exception mà không cần sửa code nghiệp vụ.

Không dùng pattern này như giải pháp “catch mọi exception mà vẫn commit”, đặc biệt khi ứng dụng có nhiều câu lệnh SQL phải thành công hoặc thất bại cùng nhau.

## 6. Spring chọn rule nào nếu có cả rollback và no-rollback?

Spring biểu diễn rule rollback bằng `RollbackRuleAttribute` và rule ngoại lệ không rollback bằng `NoRollbackRuleAttribute`. `RuleBasedTransactionAttribute.rollbackOn(Throwable)` so sánh các rule có thể khớp.

**Rule có độ sâu khớp thấp hơn (gần kiểu exception được ném hơn) thường thắng.** Có thể hiểu:

- Match trực tiếp class exception hiện tại: `depth = 0`.
- Match từ superclass gần nhất: `depth = 1`.
- Match từ superclass tiếp theo: `depth = 2`, và cứ thế.
- Không match: `depth = -1` và rule không tham gia quyết định.

Không đồng nghĩa “pattern dài hơn thì ưu tiên hơn” hay “type-based rule luôn thắng pattern-based rule”.

Ví dụ:

```java
@Transactional(
    rollbackFor = RuntimeException.class,
    noRollbackForClassName = "PaymentException"
)
public void charge() {
    // Có thể ném PaymentExceptionCritical extends RuntimeException.
}
```

Nếu `PaymentExceptionCritical` **extends RuntimeException**, hai rule đều match:

- `noRollbackForClassName="PaymentException"` khớp ngay trong tên `PaymentExceptionCritical` → `depth 0`.
- `rollbackFor=RuntimeException.class` khớp superclass `RuntimeException` → `depth 1`.
- **No-rollback rule thắng**; interceptor sẽ không chủ động rollback *chỉ vì* exception đó theo rule đã chọn.

Đây là lý do một pattern chuỗi quá rộng có thể lấn át một rule theo class mà người viết tưởng là “mạnh hơn”.

Nếu hai rule trái chiều có **cùng độ sâu** cho một exception, không nên dựa vào thứ tự khai báo để quyết định chính sách nghiệp vụ. Hãy thiết kế các rule nhất quán, không chồng lấn hoặc kiểm thử chính xác semantics của phiên bản Spring đang dùng.

### Quan hệ kế thừa khác quan hệ cause

Một ví dụ khác:

```java
@Transactional(rollbackFor = IOException.class)
public void importFile() {
    // ...
}
```

Nếu method thực tế ném `RuntimeException` bọc một `IOException` làm `cause`, rule `rollbackFor=IOException.class` **không trực tiếp match kiểu RuntimeException thông qua cause chain**. Với cấu hình thông thường, RuntimeException vẫn rollback nhờ default. Nhưng nếu có no-rollback rule cho wrapper, hoặc fallback khác, kết quả có thể thay đổi.

Muốn kiểm soát wrapper, định nghĩa rule theo **kiểu exception thật sự thoát khỏi transaction boundary** (hoặc thiết kế error translation nhất quán). Đừng nhầm substring matching của tên lớp với tìm kiếm exception message hay cause.

## 7. Ví dụ Java 17+ chạy được: đo kết quả các rule ngay từ metadata Spring

Ví dụ dùng `AnnotationTransactionAttributeSource` để đọc annotation thành `TransactionAttribute` rồi gọi `rollbackOn(Throwable)`. Đây là **API Spring thật**, cho thấy Spring chọn rollback hay không cho exception cụ thể.

Ví dụ **không mở database và không chạy giao dịch thật**; nó kiểm thử **quyết định rollback rule** một cách độc lập, có thể biên dịch/chạy bằng Java 17+ và Spring Framework 6.2.x. Để chứng minh tác động dữ liệu commit/rollback phải bổ sung integration test thực tế ở mục sau.

### 7.1. Cấu trúc dự án

```text
rollback-pattern-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── learning/
                    └── RollbackPatternDemo.java
```

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
            https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.learning</groupId>
    <artifactId>rollback-pattern-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>6.2.8</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>dev.learning.RollbackPatternDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.2. Tạo tệp `src/main/java/dev/learning/RollbackPatternDemo.java`

```java
package dev.learning;

import java.io.IOException;
import java.lang.reflect.Method;

import org.springframework.transaction.annotation.AnnotationTransactionAttributeSource;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAttribute;

public final class RollbackPatternDemo {

    // Checked exception gốc.
    public static class PaymentException extends Exception {

        // Đây là nested class, KHÔNG extends PaymentException.
        public static class DetailException extends Exception {}
    }

    // Subclass thật sự: type-based rule nên match.
    public static class PaymentExceptionSubtype extends PaymentException {}

    // Chỉ trùng tiền tố trong tên: KHÔNG extends PaymentException.
    public static class PaymentExceptionV2 extends Exception {}

    // RuntimeException trùng chuỗi, nhưng không extends PaymentException.
    public static class PaymentExceptionCritical
            extends RuntimeException {}

    public static class Rules {

        @Transactional(rollbackForClassName = "PaymentException")
        public void pattern() {}

        @Transactional(rollbackFor = PaymentException.class)
        public void typed() {}

        @Transactional(noRollbackForClassName = "PaymentException")
        public void noPattern() {}

        @Transactional(noRollbackFor = PaymentException.class)
        public void noTyped() {}

        @Transactional(rollbackForClassName = "Exception")
        public void broad() {}

        @Transactional
        public void baseline() {}

        @Transactional(
            rollbackFor = RuntimeException.class,
            noRollbackForClassName = "PaymentException"
        )
        public void competing() {}
    }

    private static final AnnotationTransactionAttributeSource SOURCE =
            new AnnotationTransactionAttributeSource();

    private static boolean shouldRollback(
            String methodName, Throwable error)
            throws NoSuchMethodException {

        Method method = Rules.class.getMethod(methodName);
        TransactionAttribute attr =
                SOURCE.getTransactionAttribute(method, Rules.class);

        if (attr == null) {
            throw new IllegalStateException(
                    "Missing @Transactional on " + methodName);
        }

        return attr.rollbackOn(error);
    }

    private static void show(
            String label, String methodName, Throwable error)
            throws NoSuchMethodException {
        System.out.println(
                label + "=" + shouldRollback(methodName, error));
    }

    public static void main(String[] args)
            throws NoSuchMethodException {

        show("pattern.exact", "pattern", new PaymentException());
        show("pattern.subtype", "pattern",
                new PaymentExceptionSubtype());
        show("pattern.suffix", "pattern",
                new PaymentExceptionV2());
        show("pattern.nested", "pattern",
                new PaymentException.DetailException());

        show("type.exact", "typed", new PaymentException());
        show("type.subtype", "typed",
                new PaymentExceptionSubtype());
        show("type.suffix", "typed", new PaymentExceptionV2());
        show("type.nested", "typed",
                new PaymentException.DetailException());

        show("noPattern.runtime", "noPattern",
                new PaymentExceptionCritical());
        show("noType.runtime", "noTyped",
                new PaymentExceptionCritical());

        show("baseline.checked", "baseline", new IOException());
        show("broad.checked", "broad", new IOException());

        show("competing.runtime", "competing",
                new PaymentExceptionCritical());
    }
}
```

**Tại sao mã là một ví dụ đúng về Spring rule matching?**

- `AnnotationTransactionAttributeSource` đọc metadata thực tế từ `@Transactional` trên `Rules`.
- `TransactionAttribute.rollbackOn(Throwable)` trả `true` nếu theo rule hiện tại cần rollback, và `false` nếu theo rule hiện tại không yêu cầu rollback.
- Các ngoại lệ đều là lớp Java được khai báo độc lập trong cùng file, giúp quan sát khác biệt giữa **Java inheritance** và **textual name matching**.
- `PaymentException.DetailException` là nested class: binary name chứa `PaymentException$DetailException` nhưng superclass là `Exception`, không phải `PaymentException`.
- `PaymentExceptionV2` là sibling checked exception; tên chứa `PaymentException` nhưng không kế thừa.
- `PaymentExceptionCritical` là runtime exception, nên mặc định rollback; no-rollback pattern vẫn có thể đảo quyết định đó.

### 7.3. Biên dịch và chạy

Trong thư mục `rollback-pattern-demo`, cần JDK 17+ và Maven; lần đầu chạy Maven cần kết nối tới kho dependency:

```bash
mvn -q clean compile exec:java
```

Các dòng chương trình in ra theo thứ tự (bỏ qua log phụ tùy cấu hình Maven):

```text
pattern.exact=true
pattern.subtype=true
pattern.suffix=true
pattern.nested=true
type.exact=true
type.subtype=true
type.suffix=false
type.nested=false
noPattern.runtime=false
noType.runtime=true
baseline.checked=false
broad.checked=true
competing.runtime=false
```

### 7.4. Đọc kết quả theo nhóm

**Nhóm pattern rollback:**

- `pattern.exact=true` đúng mục tiêu.
- `pattern.subtype=true` cũng phù hợp vì subclass của `PaymentException` sẽ có superclass chứa pattern.
- `pattern.suffix=true` chứng minh **khớp ngoài ý muốn**: `PaymentExceptionV2` không phải subclass.
- `pattern.nested=true` chứng minh nested class binary name có thể khớp dù không có quan hệ kế thừa.

**Nhóm typed rollback:**

- `type.exact=true` và `type.subtype=true` khớp đúng quan hệ type.
- `type.suffix=false` và `type.nested=false`. Hai exception này là checked, không khớp typed rule nên rơi về default policy không rollback.

**Nhóm no-rollback:**

- `noPattern.runtime=false`: một runtime exception bị loại khỏi rollback do tên chứa pattern.
- `noType.runtime=true`: type rule chỉ miễn rollback cho `PaymentException` và các subclass thật; `PaymentExceptionCritical` không thuộc nhóm đó và vẫn rollback theo default.

**Nhóm pattern rộng và rule cạnh tranh:**

- `baseline.checked=false`: `IOException` là checked exception nên không tự rollback theo default thông thường.
- `broad.checked=true`: `IOException` chứa chuỗi `Exception`, nên pattern rộng yêu cầu rollback.
- `competing.runtime=false`: no-rollback pattern match trực tiếp `PaymentExceptionCritical` ở depth 0, còn typed rollback rule `RuntimeException.class` khớp superclass ở depth 1. Rule gần hơn thắng.

**Giới hạn của demo:** đây là **transaction rule evaluation**, không có AOP proxy, JDBC connection hay commit thật. Nó kiểm chứng cơ chế so khớp; đừng dùng riêng những kết quả true/false này để tuyên bố database đã rollback hay commit.

## 8. Đưa bài học vào service có giao dịch thật

### Tình huống không mong muốn: dữ liệu vẫn commit khi runtime exception xảy ra

Trong một Spring service sử dụng `JdbcTemplate` và một `PlatformTransactionManager` đúng datasource:

```java
@Service
public class PaymentService {
    private final JdbcTemplate jdbc;

    public PaymentService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(noRollbackForClassName = "PaymentDeclinedException")
    public void charge(long orderId) {
        jdbc.update(
            "UPDATE payments SET reserved = TRUE WHERE order_id = ?",
            orderId
        );
        throw new PaymentDeclinedExceptionCritical();
    }
}
```

Đoạn này là **fragment trong ứng dụng Spring**, cần imports và lớp `PaymentDeclinedExceptionCritical extends RuntimeException`. Mục tiêu là cho thấy business method đã cập nhật hàng trước khi exception thoát. Nếu bean được gọi qua Spring proxy và không có yếu tố rollback-only nào khác, no-rollback pattern có thể khiến manager **commit** việc cập nhật `reserved` dù đã có runtime exception.

Để kiểm chứng thực sự, viết integration test: khởi tạo hàng `reserved=false`, gọi `charge(...)` qua Spring proxy và bắt exception ở **ngoài** lời gọi, sau đó truy vấn trong connection độc lập. Đọc lại `reserved` cho biết có commit hay rollback. Thử tiếp bản `noRollbackFor = PaymentDeclinedException.class` và lớp exception critical không kế thừa PaymentDeclinedException để thấy chính sách thay đổi.

Đừng dựa vào test mock chỉ xác nhận method `update(...)` được gọi. Mock không chứng minh transaction đã commit hay rollback.

### Tình huống ngược: vô tình rollback một checked exception mới

```java
@Transactional(rollbackForClassName = "GatewayTimeoutException")
public void processBatch() throws GatewayTimeoutExceptionV2 {
    // Ghi một số kết quả mà nghiệp vụ có thể muốn giữ lại.
    throw new GatewayTimeoutExceptionV2();
}
```

Đây cũng là fragment; giả sử `GatewayTimeoutExceptionV2 extends Exception` và không kế thừa `GatewayTimeoutException`. Default thông thường của Spring không rollback cho checked exception đó, nhưng pattern rollback vẫn match vì chứa chuỗi. Nếu nghiệp vụ thực sự muốn commit kết quả một phần, behavior đã khác dự kiến.

Không coi “commit một phần” là mặc nhiên đúng: ở một nghiệp vụ cần atomicity, rollback này có thể là hành vi mong muốn. **Rủi ro ở đây là cấu hình không phản ánh một quyết định chủ động về chính loại exception được ném.**

## 9. Khác biệt giữa exception type, tên class và cause

Khi một lỗi từ tầng thấp được bọc lại:

```java
try {
    gateway.call();
} catch (IOException cause) {
    throw new IllegalStateException("Gateway failed", cause);
}
```

Exception thoát khỏi transactional boundary là `IllegalStateException`, và `IOException` ở trong `cause`. Khi Spring đánh giá rollback rules, nó xét exception được ném ra qua boundary và **superclasses** của exception đó. Đừng giả định `rollbackForClassName = "IOException"` tự tìm vào `cause`.

Với `IllegalStateException`, mặc định Spring rollback bởi vì đây là `RuntimeException`. Nhưng nếu có `noRollbackForClassName="IllegalState"`, cấu hình có thể thay đổi kết quả. Đó là lý do quy tắc trên outer exception cần rõ ràng thay vì trông chờ pattern ẩn ở cause.

Mặt khác, nếu tầng repository dùng Spring exception translation để biến SQLException thành `DataAccessException` (runtime), loại exception đi ra từ service có thể khác loại do JDBC driver ném. Rule nên dựa trên **kiểu exception đã được chuyển đổi ở ranh giới service**, không dựa trên việc nhìn thấy một subclass ở tầng driver trước khi translation.

## 10. Chiến lược cấu hình an toàn

### 10.1. Ưu tiên type-safe rules khi có lớp exception

```java
@Transactional(
    rollbackFor = IOException.class,
    noRollbackFor = RecoverableBusinessException.class
)
public void handle() throws IOException {
    // ...
}
```

Fragment cần lớp `RecoverableBusinessException` thực tế. Với type rules, compiler xác minh tên lớp; refactor đổi package/class có thể cập nhật bằng IDE. `IOException.class` match `IOException` và subclasses, không match một sibling class có tên chỉ tình cờ chứa `IOException`.

**Không viết `rollbackForClassName="IOException"` khi có thể tham chiếu `IOException.class`.**

### 10.2. Nếu bắt buộc dùng ClassName, chọn tên đủ cụ thể

Đôi khi exception type nằm ở optional integration module và source code hiện tại không nên có compile-time dependency. Khi đó:

```java
@Transactional(
    rollbackForClassName =
        "com.vendor.special.GatewaySessionExpiredException"
)
public void processExternalSession() {
    // ...
}
```

Tốt hơn pattern `"Exception"` hoặc `"Session"` vì hạn chế va chạm package. **Tuy vậy, vẫn phải kiểm thử** các tên có hậu tố như `GatewaySessionExpiredExceptionV2` và nested class như `GatewaySessionExpiredException$Detail`. Không có cú pháp “exact equals” mặc định trong `rollbackForClassName`.

Nếu yêu cầu nghiệp vụ thực sự là **chỉ đúng một class, không có subclasses/suffix/nested matches**, phương án `ClassName` không diễn đạt được điều kiện so khớp chuỗi tuyệt đối. Cần đưa dependency phù hợp vào classpath và dùng type-based rule, hoặc xây chính sách lỗi trong service theo kiểu exception cụ thể và kiểm soát boundary rõ ràng.

### 10.3. Tách exception có ngữ nghĩa khác biệt

```java
class PaymentDeclinedException extends Exception {}
class PaymentInfrastructureFailure extends RuntimeException {}
```

Hai lớp có ngữ nghĩa nghiệp vụ khác nhau. Hệ phân cấp exception nên phản ánh chính sách xử lý lỗi, không chỉ thêm hậu tố `V2`/`Critical` rồi trông chờ pattern cũ loại trừ lớp mới.

Tuy nhiên **đổi tên không sửa triệt để lỗi pattern**: một dependency khác vẫn có thể thêm lớp trùng chuỗi. Điều kiện quan trọng vẫn là type safety và test.

### 10.4. Tránh positive và negative rules chồng lấn

```java
@Transactional(
    rollbackForClassName = "Exception",
    noRollbackFor = BusinessException.class
)
public void settle() {
    // ...
}
```

Pattern rộng `"Exception"` có thể match trực tiếp cùng loại `BusinessException` ở depth 0; negative typed rule cũng match tại depth 0. Trường hợp đồng hạng như vậy khó đọc và dễ thay đổi khi refactor/đổi rule order. **Tránh thiết kế xung đột cùng cấp**; định nghĩa các nhóm ngoại lệ rõ ràng và test các lớp ở ranh giới nhóm.

Cũng cần lưu ý: **một rule cụ thể trong `@Transactional` không thay thế mọi quy tắc khác**. Nếu exception chưa khớp rule nào, fallback mặc định vẫn có thể rollback runtime errors. Nếu exception khớp no-rollback rule nhưng underlying transaction đã rollback-only, physical commit vẫn có thể không thành công.

### 10.5. Review theo hành vi, không chỉ theo annotation

Mỗi khi thấy `rollbackForClassName` hoặc `noRollbackForClassName` trong code review, hỏi:

- Những exception classes **có thể thực tế thoát** khỏi method qua Spring proxy là gì?
- Có subclass, sibling với hậu tố, nested class hoặc cùng simple name ở package khác không?
- Exception nào được wrapper hoặc translator thay đổi kiểu trước khi thoát?
- Có rollback/no-rollback rules khác cạnh tranh, và độ sâu rule nào thắng?
- Rule mang tính nghiệp vụ hay đang che đi việc exception bị bắt nuốt không?
- Điều gì xảy ra với dữ liệu đã ghi khi exception được ném: commit, rollback, hay database tự chuyển rollback-only?

Nếu không trả lời được bằng test, pattern đang có thể là một phụ thuộc hành vi ngầm.

## 11. Bộ test hồi quy nên có

### Test rule matching thuần (nhanh, không cần database)

Ví dụ mục 7 đã cung cấp cách test `TransactionAttribute.rollbackOn(Throwable)`:

| Trường hợp | Pattern-based rule | Type-based rule mong muốn |
| --- | --- | --- |
| Exception đúng tên | Match | Match |
| Subclass thật của exception cấu hình | Match (qua superclass) | Match |
| Sibling `...ExceptionV2` có tên chứa pattern | **Có thể match ngoài ý muốn** | Không match |
| Nested `...Exception$Detail` không kế thừa | **Có thể match ngoài ý muốn** | Không match |
| Exception cùng simple name ở package khác | Có thể match với simple-name pattern | Không match nếu type không cùng class |
| Runtime exception có tên chứa `noRollbackForClassName` | Có thể bị loại khỏi rollback mặc định | Type rule không tác động nếu không có quan hệ kế thừa |
| Broad `"Exception"` đối với `IOException` | Match | `Exception.class` cũng match theo type nhưng rõ ràng hơn |

### Integration test với transaction manager và database thật

1. **Prepare:** tạo dữ liệu ban đầu trong transaction đã commit; biết chính xác các hàng.
2. **Invoke:** gọi service bean qua Spring proxy, không qua `new` hoặc `this.method()`.
3. **Cause failure:** tạo một lỗi sau khi đã thực thi thao tác ghi; dùng exception class mong muốn và class có tên gần giống để phân biệt.
4. **Observe:** sau khi phương thức kết thúc/throw exception, đọc dữ liệu bằng connection/transaction độc lập. Chỉ kiểm tra mock invocation không đủ.
5. **Assert:** trường hợp được rollback thì dữ liệu trở về trạng thái đầu; trường hợp no-rollback theo nghiệp vụ thì chỉ các thay đổi được cho phép mới tồn tại.
6. **Repeat:** đổi lớp exception thành `...V2` hoặc nested class, kiểm tra rule vẫn phản ánh chính sách mong muốn.

Một lưu ý khi dùng Spring TestContext: test method có `@Transactional` có thể được framework rollback ở cuối test, khiến việc quan sát commit của service trở nên sai lệch. Để test **commit thực tế của service**, hãy thiết kế test không bao quanh nó bằng một test-managed transaction không cần thiết, hoặc dùng `TestTransaction` phù hợp để kiểm soát ranh giới test.

### Khi cần xác nhận precedence

Trong unit test, kiểm tra `RollbackRuleAttribute.getDepth(Throwable)` hoặc kết quả cuối từ `RuleBasedTransactionAttribute.rollbackOn(Throwable)`. Đừng chỉ kiểm tra có rule nằm trong annotation; hãy kiểm tra **exception thực tế** và tập rule đầy đủ.

Một ứng dụng có thể thay đổi rule mặc định theo phiên bản/cấu hình Spring. Vì vậy test regression phải dựa trên cùng phiên bản và transaction configuration ứng dụng đang deploy.

## 12. Những hiểu lầm phổ biến

**“Đã ghi đầy đủ package nên ClassName là exact match.”** Sai. Pattern fully qualified vẫn có thể match hậu tố `V2` và nested `$Detail`.

**“Pattern `*Exception` dùng wildcard như glob.”** Sai. Spring không coi `*` là wildcard trong các rollback rule patterns này.

**“`rollbackForClassName` chỉ kiểm tra tên simple class, không xét superclass.”** Sai. Spring có thể đi lên superclass hierarchy; match ở superclass có depth lớn hơn match trực tiếp.

**“Một typed rule luôn được ưu tiên trước một string pattern.”** Sai. Cơ chế chọn winner dựa vào **độ sâu khớp**, nên pattern trực tiếp có thể thắng typed superclass rule.

**“`noRollbackForClassName` chỉ xử lý checked exceptions.”** Sai. Nó có thể match `RuntimeException`, làm thay đổi hành vi rollback mặc định rất quan trọng.

**“`noRollbackForClassName` bảo đảm transaction commit sau lỗi.”** Sai. Nó thay đổi quyết định rollback theo exception; commit vẫn có thể thất bại nếu database/resource báo lỗi hoặc transaction đã rollback-only.

**“Rule rollback tự động duyệt `getCause()`.”** Sai với semantics khớp exception/superclass được mô tả. Nếu exception bị wrap, quy tắc phải phù hợp với exception được đánh giá ở boundary.

**“Nếu Unit test rollbackOn(...) pass thì không cần integration test.”** Sai. Unit test chỉ cho biết quy tắc lựa chọn. Cần test trên transaction manager + datasource thực sự để xác nhận dữ liệu được commit/rollback như thiết kế.

## 13. Checklist chọn cấu hình

- [ ] Nếu biết exception class ở compile time, dùng `rollbackFor = X.class` hoặc `noRollbackFor = X.class`.
- [ ] Nếu dùng `ClassName` vì ràng buộc module, đã ghi tên đủ đặc trưng và tài liệu hóa lý do.
- [ ] Không dùng pattern cực rộng như `"Exception"` một cách vô thức, đặc biệt với `noRollbackForClassName`.
- [ ] Đã xét va chạm package, hậu tố `V2`, nested `$` và class có cùng simple name.
- [ ] Đã hiểu superclass matching, rule depth và fallback mặc định.
- [ ] Không có các rule mâu thuẫn cùng độ sâu mà kết quả phụ thuộc thứ tự khó nhận ra.
- [ ] Đã thử checked exception, runtime exception và exception được wrap/translate.
- [ ] Đã xác nhận method được chặn qua Spring proxy và resource tham gia đúng transaction manager.
- [ ] Đã kiểm thử dữ liệu sau khi method throw, bao gồm trường hợp cố ý commit và rollback.
- [ ] Đã xem lại semantics khi nâng cấp Spring hoặc đổi default rollback policy.

## 14. Tự kiểm tra

**Câu 1.** `rollbackForClassName = "com.acme.CustomException"` có khớp `com.acme.CustomExceptionV2` dù không có quan hệ kế thừa không?

Có. Tên của lớp thứ hai chứa toàn bộ chuỗi pattern. Đó chính là lý do FQCN vẫn không bảo đảm exact matching.

**Câu 2.** `noRollbackForClassName = "Exception"` có thể làm `NullPointerException` không rollback không?

Có. `NullPointerException` là runtime exception, tên chứa `Exception`. Nếu rule này thắng và transaction chưa rollback-only, manager có thể cố commit thay vì rollback theo default.

**Câu 3.** Rule `rollbackFor = CustomException.class` có khớp `CustomException$NestedException` không?

Chỉ khi nested exception **thật sự kế thừa `CustomException`**. Việc nested class có binary name chứa chuỗi `CustomException` tự nó không làm type-based rule match.

**Câu 4.** Vì sao `noRollbackForClassName="PaymentException"` có thể thắng `rollbackFor=RuntimeException.class` với `PaymentExceptionCritical extends RuntimeException`?

Pattern match tên `PaymentExceptionCritical` trực tiếp ở depth 0, còn typed `RuntimeException` match ở superclass depth 1. Winner theo độ sâu thấp hơn.

**Câu 5.** `rollbackForClassName="IOException"` có tự match một `IllegalStateException` với `IOException` trong cause không?

Không theo cơ chế kiểm tra tên lớp và superclass được mô tả. Cần tính đến kiểu exception thực tế thoát qua transaction boundary; trong trường hợp đó `IllegalStateException` có thể rollback theo default runtime policy.

**Câu 6.** Làm sao chứng minh một no-rollback rule ảnh hưởng commit thật?

Tạo integration test với dữ liệu đã commit trước đó, gọi service qua proxy, gây exception sau khi ghi, rồi truy vấn từ connection độc lập sau khi transaction kết thúc. So sánh actual data với chính sách nghiệp vụ mong muốn.

## 15. Kết luận cần thuộc

- **`rollbackForClassName`/`noRollbackForClassName` khớp substring của tên exception class**, không phải so khớp kiểu Java và không phải wildcard/regex.
- **Tên tương tự, hậu tố `V2`, cùng simple name và nested class `$`** có thể khiến rule áp dụng cho exception khác với dự định.
- **`noRollbackForClassName` quá rộng đặc biệt rủi ro** vì có thể biến lỗi runtime cần rollback thành yêu cầu commit.
- **Strongest matching rule** được quyết định bằng độ sâu khớp trong exception superclass hierarchy, không chỉ dựa vào tên attribute hay độ dài pattern.
- **Ưu tiên `rollbackFor`/`noRollbackFor` dạng `Class` khi có thể**; nếu buộc dùng chuỗi thì viết integration/unit tests với các tên gần giống và ngoại lệ được wrap.
- **Quyết định rollback không đồng nghĩa kết quả commit vật lý**: database, transaction manager, rollback-only và resource participation vẫn quyết định kết quả cuối.

## Tài liệu tham khảo chính thức

1. [Spring Framework 6.2 — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html): so sánh type-based và pattern-based rules, cảnh báo false positives với tên tương tự/nested class, strongest matching rule.
2. [Spring Framework 6.2 — `@Transactional` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html): semantics của `rollbackFor`, `noRollbackFor`, `rollbackForClassName` và `noRollbackForClassName`.
3. [Spring Framework 6.2 — `RollbackRuleAttribute` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/interceptor/RollbackRuleAttribute.html): constructor theo kiểu/pattern, `getDepth(Throwable)` và matching superclass.
4. [Spring Framework 6.2 — `NoRollbackRuleAttribute` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/interceptor/NoRollbackRuleAttribute.html): ý nghĩa của rule phủ định.
5. [Spring Framework 6.2 — `RuleBasedTransactionAttribute` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/interceptor/RuleBasedTransactionAttribute.html): `rollbackOn(Throwable)` và quy tắc chọn winner.
6. [Spring Framework 6.2 — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html): defaults và hỗ trợ rollback policy toàn cục từ Spring 6.2.
