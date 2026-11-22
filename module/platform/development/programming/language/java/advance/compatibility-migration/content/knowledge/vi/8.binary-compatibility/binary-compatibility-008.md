# Thêm abstract method hoặc default method và thời điểm phát sinh lỗi

Khi một thư viện Java thay đổi interface hoặc abstract class, hai phiên bản có thể **biên dịch thành công độc lập** nhưng lại không chạy được cùng nhau. Tình huống thường gặp là phiên bản mới thêm một phương thức `abstract` mà các implementation cũ chưa cài đặt, hoặc thêm một phương thức `default` vào interface khiến nhiều implementation kế thừa hai phương thức mặc định xung đột. Điều đặc biệt là lỗi không nhất thiết xuất hiện khi JVM khởi động hoặc khi class được nạp; nó có thể chỉ xuất hiện khi một lời gọi phương thức cụ thể được thực hiện.

Để đánh giá đúng tương thích nhị phân (binary compatibility), cần phân biệt **biên dịch lại source**, **chạy class file đã biên dịch trước đó**, **tra cứu và phân giải phương thức**, và **thời điểm JVM thực sự gọi phương thức**. Cùng một thay đổi API có thể an toàn với consumer cũ không sử dụng tính năng mới, nhưng gây lỗi cho consumer mới khi nó gọi tính năng ấy trên implementation cũ.

## 1. Phân biệt abstract method, default method và implementation

Trong Java, một interface có thể khai báo phương thức trừu tượng hoặc phương thức mặc định:

~~~java
public interface NotificationSender {
    void send(String message);  // abstract method

    default boolean supportsRetry() {
        return false;
    }
}
~~~

- **Abstract method:** chỉ công bố hợp đồng, không cung cấp thân phương thức. Một lớp concrete triển khai interface thường phải có implementation phù hợp, trực tiếp hoặc qua lớp cha.
- **Default method:** có thân phương thức ngay trong interface. Một lớp implement interface có thể thừa hưởng implementation này nếu không có phương thức phù hợp trong class hierarchy hoặc xung đột giữa các interface.
- **Concrete method của class:** phương thức có phần triển khai trong class hoặc superclass. Khi giải quyết cùng chữ ký, các phương thức instance phù hợp từ class hierarchy có ưu tiên so với default method từ interface.

Một abstract class cũng có thể chứa abstract method:

~~~java
public abstract class ReportGenerator {
    public abstract byte[] generate();
}
~~~

Khác với interface, class Java không dùng từ khóa `default` để khai báo default method. Một phương thức concrete thông thường trong superclass cung cấp implementation kế thừa cho subclass; interface default method là cơ chế riêng được bổ sung từ Java 8.

Về bytecode, một abstract method có cờ `ACC_ABSTRACT` và không có thân `Code`. Interface default method là interface instance method có phần `Code` và không mang `ACC_ABSTRACT`; `default` là khái niệm ngôn ngữ, không phải một cờ `ACC_DEFAULT` độc lập trong class file.

## 2. Vì sao thêm abstract method có thể tạo lỗi muộn?

Giả sử một thư viện phát hành interface phiên bản 1:

~~~java
// api-v1/demo/Job.java
package demo;

public interface Job {
}
~~~

Một ứng dụng khác biên dịch implementation dựa trên phiên bản này:

~~~java
// impl-v1/demo/LegacyJob.java
package demo;

public final class LegacyJob implements Job {
}
~~~

Ở thời điểm đó, `LegacyJob` là concrete class hợp lệ vì interface `Job` chưa yêu cầu phương thức nào. Class file của nó ghi nhận việc triển khai `demo.Job`, nhưng không có method `run()`.

Sau đó, nhà cung cấp phát hành interface phiên bản 2:

~~~java
// api-v2/demo/Job.java
package demo;

public interface Job {
    void run();
}
~~~

Nếu lấy **source** của `LegacyJob` và biên dịch lại cùng `Job` v2, compiler báo lỗi vì class concrete chưa triển khai `run()`. Đây là vấn đề **source compatibility**.

Tuy nhiên, **class file `LegacyJob` đã biên dịch bằng v1 có thể vẫn được nạp và tạo đối tượng** khi runtime sử dụng `Job` v2. JVM không yêu cầu mọi concrete class file cũ phải vượt qua lại toàn bộ phép kiểm tra source-level của compiler mới khi class được load. Thay đổi này nhìn chung được xem là tương thích nhị phân đối với các binary cũ trong phạm vi chúng vẫn dùng các lời gọi đã tồn tại.

Một consumer được biên dịch dựa trên API v2 có thể viết:

~~~java
// client-v2/demo/NewCaller.java
package demo;

public final class NewCaller {
    public static void main(String[] args) {
        Job job = new LegacyJob(); // class file LegacyJob từ v1
        job.run();                  // phương thức mới trong Job v2
    }
}
~~~

Khi chạy với `Job` v2 và binary `LegacyJob` v1, lời gọi `job.run()` không tìm được implementation concrete phù hợp trên đối tượng nhận. JVM có thể ném:

~~~text
java.lang.AbstractMethodError
~~~

Điểm cần nhớ: **lỗi nằm ở lời gọi phương thức mới trên implementation cũ**. Việc class đã được nạp, constructor đã chạy hoặc một phương thức cũ khác hoạt động bình thường không chứng minh `run()` sẽ gọi được.

### 2.1. Vì sao đây không nhất thiết là NoSuchMethodError?

Trong tình huống trên, interface v2 **có** khai báo `Job.run()`. Tham chiếu phương thức trong bytecode của caller có thể được phân giải tới khai báo đó. Vấn đề xuất hiện khi JVM cần tìm implementation concrete để thực hiện lời gọi trên đối tượng `LegacyJob` và không tìm được.

Do đó, trường hợp điển hình là `AbstractMethodError`. Ngược lại, nếu lời gọi cũ tham chiếu tới một phương thức đã bị xóa hoặc đổi descriptor và lookup không tìm được phương thức phù hợp, có thể xuất hiện `NoSuchMethodError`. Hai lỗi chỉ ra hai dạng khác nhau của sự cố liên kết/chọn phương thức.

### 2.2. Khi nào không có lỗi?

Thêm abstract method vào interface không đồng nghĩa mọi implementation cũ đều lỗi ngay:

- Consumer cũ không có lời gọi tới method mới thì có thể tiếp tục chạy bình thường.
- Implementation cũ tình cờ đã có public instance method với chữ ký và kiểu trả về phù hợp thì method đó có thể đáp ứng hợp đồng mới.
- Implementation mới được biên dịch lại và cài đặt method thì lời gọi có implementation hợp lệ.
- Một lớp abstract trung gian có thể tiếp tục để method chưa được triển khai cho subclass concrete thực hiện theo thiết kế.

Vì vậy, phải ghi rõ **cặp phiên bản** và **đường gọi thực tế**, thay vì kết luận chung rằng “thêm abstract method luôn phá binary compatibility” hoặc “thêm method luôn an toàn”.

## 3. Phân biệt thời điểm biên dịch, nạp lớp và gọi phương thức

Cùng ví dụ `Job` ở trên, các mốc có thể được mô tả như sau:

~~~text
Thời điểm A: Biên dịch implementation với Job v1
  Job v1 {} + LegacyJob implements Job
                     |
                     v
             LegacyJob.class hợp lệ

Thời điểm B: Provider phát hành Job v2
  Job v2 { abstract void run(); }
                     |
                     v
           Binary LegacyJob v1 vẫn tồn tại

Thời điểm C: Chạy với Job v2 + LegacyJob.class v1
  Load Job v2, load LegacyJob, tạo đối tượng
                     |
                     v
              Có thể thành công
                     |
                     v
           invokeinterface Job.run()
                     |
                     v
         Không có implementation concrete
                     |
                     v
               AbstractMethodError
~~~

JVM có thể thực hiện một số thao tác liên kết và phân giải tham chiếu sớm hoặc trì hoãn. Vì vậy, **không được dùng thời điểm class loading như một quy tắc tuyệt đối cho mọi lỗi**. Trong ví dụ này, điều quan trọng ở mức quan sát là chương trình chỉ cần method mới khi thực hiện lời gọi, và lỗi thiếu implementation có thể xuất hiện ở lần gọi đó.

Đối với hệ thống lớn, đường gọi có thể chỉ được thực hiện khi có request đặc biệt, message hiếm, tác vụ theo lịch hoặc một tính năng mới được bật bằng feature flag. Ứng dụng chạy nhiều ngày mà không gặp lỗi vẫn có thể chứa một tổ hợp binary chưa tương thích.

## 4. Ví dụ thực hành tái hiện lỗi với hai bản API

Có thể tạo bốn thư mục source như ví dụ trước và biên dịch theo thứ tự: API v1, implementation v1, API v2, caller v2. Các lệnh dưới đây minh họa trên Windows PowerShell, nơi classpath dùng dấu `;`:

~~~powershell
javac -d build\api-v1 api-v1\demo\Job.java
javac -cp build\api-v1 -d build\impl-v1 impl-v1\demo\LegacyJob.java
javac -d build\api-v2 api-v2\demo\Job.java

javac -cp 'build\api-v2;build\impl-v1' -d build\client-v2 client-v2\demo\NewCaller.java

java -cp 'build\api-v2;build\impl-v1;build\client-v2' demo.NewCaller
~~~

Trên Linux/macOS, classpath thường dùng dấu `:`. Các đường dẫn trong ví dụ giả định đã tạo các thư mục source và output tương ứng. Mục đích là **giữ nguyên class file implementation được biên dịch với API v1**, sau đó chạy nó cùng API v2. Nếu biên dịch lại implementation theo v2, lỗi sẽ được phát hiện ở compile time và không còn tái hiện tình huống binary cũ.

Để quan sát tham chiếu của caller và phần khai báo phương thức, có thể dùng:

~~~powershell
javap -classpath build\client-v2 -c -v demo.NewCaller
javap -classpath build\api-v2 -p -s demo.Job
javap -classpath build\impl-v1 -p -s demo.LegacyJob
~~~

Trong bytecode caller, tìm instruction `invokeinterface` và symbolic reference tới `demo.Job.run:()V`. Trong interface v2, `run()` tồn tại nhưng không có implementation; trong `LegacyJob.class` v1, phương thức tương ứng không được khai báo. Đây là bằng chứng trực tiếp cho tình huống `AbstractMethodError`.

## 5. Thêm default method: trường hợp mở rộng hoạt động được

Một cách mở rộng interface mà không buộc implementation cũ thêm code là cung cấp hành vi mặc định:

~~~java
// api-v1/demo/Task.java
package demo;

public interface Task {
    void execute();
}
~~~

Implementation cũ:

~~~java
package demo;

public final class OldTask implements Task {
    @Override
    public void execute() {
        System.out.println("executed");
    }
}
~~~

API v2 bổ sung method có phần triển khai:

~~~java
// api-v2/demo/Task.java
package demo;

public interface Task {
    void execute();

    default boolean isCancelable() {
        return false;
    }
}
~~~

Khi một caller mới gọi `isCancelable()` trên `OldTask.class` đã biên dịch bằng API v1, JVM có thể chọn implementation mặc định từ `Task` v2. `OldTask` không nhất thiết phải được biên dịch lại để thừa hưởng method này.

Hành vi mặc định `false` ở đây chỉ là ví dụ: nó có ý nghĩa như “implementation cũ không hỗ trợ hủy”. Một method mặc định được thêm vào nên có hành vi an toàn và đúng hợp đồng. Một default method âm thầm bỏ qua thao tác thanh toán, kiểm tra quyền hoặc cập nhật dữ liệu có thể khiến hệ thống đưa ra kết quả sai dù hoàn toàn không phát sinh linkage error.

### 5.1. Khi class đã có method trùng chữ ký

Nếu `OldTask` hoặc superclass của nó đã có public instance method `isCancelable()` tương thích, implementation của class được ưu tiên so với default method trong interface. Điều này cho phép hành vi đặc thù của class tiếp tục có hiệu lực, nhưng cũng có thể làm phương thức vốn không được thiết kế để triển khai hợp đồng mới trở thành implementation của hợp đồng đó.

Ví dụ, một class cũ có method `reset()` dùng để đặt lại giao diện; interface mới bổ sung `default reset()` với ý nghĩa đặt lại giao dịch. JVM có thể dùng method của class vì tên và descriptor khớp, nhưng ngữ nghĩa lại không giống nhau. Đây là **rủi ro behavioral compatibility**, không thể phát hiện chỉ bằng việc chương trình chạy không lỗi.

### 5.2. Khi một subinterface có default method cụ thể hơn

Giả sử:

~~~java
interface Parent {
    default String label() {
        return "parent";
    }
}

interface Child extends Parent {
    @Override
    default String label() {
        return "child";
    }
}

final class Example implements Child {
}
~~~

`Example` thừa hưởng `Child.label()` vì đây là khai báo default cụ thể hơn trong quan hệ kế thừa interface. Không nên hiểu rằng mọi interface có default cùng chữ ký đều gây xung đột: **quan hệ kế thừa và quy tắc chọn phương thức** quyết định method nào phù hợp.

## 6. Thêm default method cũng có thể tạo xung đột runtime

Một trường hợp nguy hiểm là implementation cũ đã triển khai hai interface độc lập. Khi một interface được nâng cấp và bổ sung default method trùng chữ ký với default method của interface còn lại, binary cũ có thể trở nên mơ hồ khi gọi phương thức.

Phiên bản 1 của hai interface:

~~~java
// Interface A v1
public interface A {
    default String label() {
        return "A";
    }
}
~~~

~~~java
// Interface B v1
public interface B {
}
~~~

Implementation được biên dịch với A v1 và B v1:

~~~java
public final class Legacy implements A, B {
    // Không khai báo label(); thừa hưởng A.label().
}
~~~

Caller cũ có thể gọi:

~~~java
Legacy legacy = new Legacy();
System.out.println(legacy.label());
~~~

Sau đó B v2 thêm default method cùng tên và descriptor:

~~~java
// Interface B v2
public interface B {
    default String label() {
        return "B";
    }
}
~~~

Nếu **giữ nguyên `Legacy.class` và caller cũ**, chỉ thay B v1 bằng B v2, class `Legacy` có thể vẫn được nạp. Nhưng khi lời gọi `label()` cần chọn implementation, JVM có hai default method cùng độ ưu tiên từ hai interface độc lập A và B. Trường hợp xung đột như vậy có thể ném:

~~~text
java.lang.IncompatibleClassChangeError: Conflicting default methods
~~~

Nếu lấy **source** `Legacy` và biên dịch lại với A v1/B v2, `javac` phát hiện xung đột phương thức mặc định và yêu cầu class giải quyết. Vì vậy lỗi khi biên dịch lại và lỗi khi chạy binary cũ xảy ra ở **hai thời điểm khác nhau**.

### 6.1. Giải quyết xung đột bằng implementation rõ ràng

Khi có quyền sửa class, có thể override phương thức và chỉ rõ ý nghĩa mong muốn:

~~~java
public final class Legacy implements A, B {
    @Override
    public String label() {
        return A.super.label();
    }
}
~~~

Lúc này class có implementation riêng, nên không còn cần JVM chọn giữa hai default độc lập. `A.super.label()` là cú pháp dùng để gọi trực tiếp default method mong muốn từ interface khi phù hợp với quy tắc kế thừa.

Nếu class cũ được phát hành bởi bên thứ ba và không thể biên dịch lại ngay, provider phải cân nhắc giữ API cũ, đổi thiết kế phương thức mới hoặc cung cấp phiên bản tương thích khác. Chỉ nâng version dependency rồi kỳ vọng xung đột tự biến mất là không đủ.

## 7. Thêm abstract method vào abstract class

Tình huống tương tự xảy ra với abstract superclass được bên ngoài mở rộng.

Phiên bản 1:

~~~java
public abstract class Workflow {
    public void start() {
        System.out.println("started");
    }
}
~~~

Subclass được biên dịch bằng v1:

~~~java
public final class LegacyWorkflow extends Workflow {
}
~~~

Phiên bản 2 bổ sung abstract method vào **lớp vốn đã abstract**:

~~~java
public abstract class Workflow {
    public void start() {
        System.out.println("started");
    }

    public abstract void stop();
}
~~~

Khi biên dịch lại source `LegacyWorkflow` với v2, compiler yêu cầu class concrete triển khai `stop()`. Nhưng binary cũ của `LegacyWorkflow` có thể vẫn được nạp và tạo đối tượng với superclass mới; nó chưa chắc gây lỗi ở thời điểm khởi tạo. Khi caller mới thực sự gọi `stop()` mà không có concrete implementation, có thể phát sinh `AbstractMethodError`.

Phải phân biệt trường hợp này với việc **biến một class trước đây concrete thành abstract**. Nếu binary cũ có instruction `new Workflow` và class runtime nay là abstract, việc tạo instance có thể gây `InstantiationError`. Đây là thay đổi khác về tính instantiable của class, không chỉ là thêm abstract method vào một abstract superclass đang tồn tại.

## 8. Trường hợp interface được dùng làm functional interface

Functional interface có đúng một abstract method theo quy tắc của Java, cho phép dùng lambda hoặc method reference làm implementation. Thêm một abstract method có thể khiến interface không còn là functional interface khi biên dịch source mới.

Ví dụ ban đầu:

~~~java
@FunctionalInterface
public interface Processor {
    void process(String value);
}

Processor p = value -> System.out.println(value);
~~~

Nếu phiên bản mới thêm:

~~~java
void cancel();
~~~

Compiler có thể báo rằng interface không còn là functional interface; source dùng lambda không biên dịch lại được. Bỏ `@FunctionalInterface` cũng không giải quyết vấn đề: có hai abstract method độc lập thì lambda không còn đủ để cài đặt hợp đồng.

Một lambda đã được biên dịch với bản cũ sử dụng cơ chế runtime phù hợp với bản compiler tạo ra. Không nên giả định việc load và mọi lời gọi trên binary này sẽ thất bại ngay lập tức; rủi ro đáng chú ý là lời gọi phương thức mới mà implementation cũ không cung cấp. Cần kiểm thử với artifact thật nếu ứng dụng trộn các thế hệ thư viện.

Nếu method mới có thể cung cấp hành vi mặc định, thêm `default void cancel() { ... }` có thể giữ số abstract method không đổi. Dù vậy, default implementation phải đúng về nghiệp vụ. Không nên tạo một method no-op chỉ để giữ compiler im lặng khi consumer cần biết thao tác hủy có được thực hiện hay không.

## 9. Bảng đối chiếu tác động và thời điểm phát sinh lỗi

| Thay đổi trong API | Biên dịch lại implementation cũ | Chạy binary implementation cũ | Lỗi điển hình và thời điểm |
|---|---|---|---|
| Thêm abstract method vào interface | Concrete class thường phải cài đặt method mới | Có thể load/chạy các method cũ | `AbstractMethodError` khi gọi method mới mà không có implementation |
| Thêm default method không xung đột | Thường không cần implementation mới | Có thể thừa hưởng method mặc định | Không có linkage error nếu lookup/dispatch hợp lệ; vẫn cần kiểm tra hành vi |
| Thêm default trùng với default độc lập | Có thể báo lỗi xung đột khi biên dịch lại | Binary cũ có thể load | `IncompatibleClassChangeError` khi lời gọi cần chọn giữa các default xung đột |
| Thêm abstract method vào abstract superclass | Concrete subclass phải implement khi biên dịch lại | Subclass binary cũ có thể load | `AbstractMethodError` khi lời gọi cần method chưa được triển khai |
| Đổi class concrete thành abstract | Source tạo instance không còn biên dịch | Binary cũ có thể chứa instruction `new` | `InstantiationError` khi cố tạo instance của class nay abstract |
| Xóa method hoặc đổi descriptor | Caller source cũ có thể không biên dịch | Caller binary cũ mang tham chiếu không còn phù hợp | `NoSuchMethodError` khi tham chiếu không phân giải được |

Đây là các tình huống **điển hình**, không phải lời khẳng định mọi thay đổi đều luôn sinh đúng một loại lỗi. Kết quả còn phụ thuộc method nào được gọi, class hierarchy, implementation kế thừa, signature, quyền truy cập, class loader và tổ hợp phiên bản thực tế.

## 10. Vì sao lỗi có thể chỉ xuất hiện ở production?

Trong phát triển, nhóm thường biên dịch lại toàn bộ module cùng một phiên bản dependency. Khi đó compiler phát hiện class thiếu abstract method hoặc conflict giữa hai default. Nhưng production có thể khác:

- **Plugin cũ:** hệ thống chính nâng interface, plugin của đối tác vẫn giữ binary cũ.
- **Rolling deployment:** một số instance dùng API mới, một số component vẫn là implementation cũ.
- **Ứng dụng mobile hoặc client lâu cập nhật:** consumer/adapter phát hành độc lập, không được biên dịch lại cùng backend.
- **Classpath conflict:** runtime chọn JAR khác với JAR dùng ở compile time.
- **Container và app server:** class được nạp từ loader hoặc deployment khác dự kiến.
- **Đường gọi hiếm:** method mới chỉ được dùng khi có một tác vụ hoặc feature flag cụ thể.
- **Generated code:** framework/plugin sinh implementation ở build trước nhưng runtime được nâng API sau.

Một test chỉ kiểm tra khởi động ứng dụng có thể bỏ sót tất cả trường hợp trên. Cần chạy những lời gọi thực tế đi qua interface hoặc abstract superclass thay đổi, bao gồm implementation của các phiên bản vẫn còn được hỗ trợ.

## 11. Cách điều tra AbstractMethodError và default-method conflict

Khi gặp `AbstractMethodError` hoặc `IncompatibleClassChangeError` sau migration, có thể điều tra theo trình tự:

1. **Ghi stack trace và method được gọi.** Xác định owner type, tên và descriptor xuất hiện trong thông báo hoặc ở frame liên quan.
2. **Xác định binary caller.** Lời gọi được biên dịch với API phiên bản nào? Có compiler output hoặc artifact checksum để truy vết không?
3. **Xác định runtime API.** JAR interface/abstract class nào được JVM thực tế nạp?
4. **Xác định implementation thực tế.** Object thuộc class nào, do loader nào định nghĩa và class đó được build từ phiên bản nào?
5. **Đọc hierarchy.** Class/superclass có method concrete phù hợp không? Các interface có default method nào có thể xung đột?
6. **Xem bytecode.** Dùng `javap -v -c -s` để đọc symbolic reference và instruction gọi phương thức.
7. **Tái hiện tổ hợp version.** Giữ nguyên binary cũ và chỉ thay dependency đích để kiểm tra kết quả.
8. **Sửa theo hợp đồng.** Bổ sung implementation, điều chỉnh default method, giữ API cũ hoặc nâng đồng bộ consumer theo kế hoạch.

Các lệnh hỗ trợ:

~~~bash
# Xem chữ ký và descriptor của interface/abstract class
javap -classpath api-v2.jar -p -s com.example.api.Task

# Xem method và bytecode của caller
javap -classpath client.jar -v -c -s com.example.client.TaskCaller

# Xem implementation đã được biên dịch từ bản cũ
javap -classpath legacy-implementation.jar -p -s com.example.impl.OldTask

# Liệt kê class trong artifact
jar tf legacy-implementation.jar
~~~

Lệnh trên chỉ minh họa cách khảo sát; cần thay tên package, class và artifact bằng hệ thống thực tế. Với modular JAR, kiểm tra thêm `module-info`, exports và khả năng đọc module. Với class loader tùy chỉnh, không nên suy ra JAR được nạp từ classpath dựa trên tên file trong build script.

Đối với các JDK có unified logging, có thể dùng log class loading khi phù hợp:

~~~bash
java -Xlog:class+load=info -jar application.jar
~~~

Log này giúp lần theo nguồn nạp class nhưng có thể tạo nhiều dữ liệu. Chỉ bật ở môi trường và thời gian phù hợp, sau đó tìm class/interface liên quan trong log.

## 12. Thiết kế API để hạn chế rủi ro khi phát hành

### 12.1. Nếu bắt buộc bổ sung hành vi mới

Khi một hành vi mới thật sự bắt buộc với mọi implementation, provider có thể cần phát hành thay đổi không tương thích ở mức source hoặc yêu cầu các implementation nâng cấp. Cần công bố trước điều kiện hỗ trợ, liệt kê nhóm consumer/plugin bị tác động và chạy test với implementation cũ còn tồn tại.

Một lựa chọn khác là tạo interface mở rộng:

~~~java
public interface Job {
    void run();
}

public interface CancelableJob extends Job {
    void cancel();
}
~~~

Consumer có thể kiểm tra capability thay vì gọi `cancel()` trên mọi `Job`:

~~~java
public void requestCancel(Job job) {
    if (job instanceof CancelableJob) {
        ((CancelableJob) job).cancel();
    } else {
        throw new UnsupportedOperationException("Job không hỗ trợ hủy");
    }
}
~~~

Cách này làm rõ rằng không phải mọi implementation cũ đều có khả năng hủy. Không cần thêm abstract method trực tiếp vào `Job`, giúp giữ hợp đồng của các implementor hiện có.

### 12.2. Nếu bổ sung default method

Chỉ dùng default method khi có thể cung cấp implementation có ngữ nghĩa nhất quán cho tất cả implementor cũ. Cần kiểm tra:

- Method mới có trùng tên/descriptor với method ở interface khác mà consumer đang implement không?
- Có class hoặc superclass đang cung cấp method cùng chữ ký và ngữ nghĩa khác không?
- Default implementation có đúng với mọi implementation cũ không?
- Có gây thay đổi behavior, side effect, security hoặc transaction không?
- Có phù hợp khi caller dùng reflection, proxy, AOP hoặc generated code không?
- Có ảnh hưởng tới thứ tự chọn method khi framework introspect interface không?

Nếu hành vi mặc định không thể đáp ứng yêu cầu an toàn, nên dùng interface mới, capability discovery hoặc migration theo giai đoạn. Một default method chỉ để ném `UnsupportedOperationException` có thể làm hợp đồng rõ hơn về khả năng chưa hỗ trợ, nhưng vẫn cần consumer chủ động xử lý; đây không phải lời hứa rằng mọi lời gọi mới sẽ chạy thành công.

### 12.3. Chính sách version và deprecation

Thêm abstract method có thể được phân loại là binary-compatible theo một nghĩa nhất định của đặc tả nhưng lại gây source incompatibility cho implementation cũ và `AbstractMethodError` khi có caller mới. Vì vậy, cách đánh số phiên bản và release notes cần dựa vào đối tượng người dùng thư viện và các tổ hợp deployment được hỗ trợ.

Đánh dấu API cũ `@Deprecated` là một bước truyền đạt ý định, không tự giúp implementation cũ hỗ trợ abstract method mới. Nếu thay đổi không tương thích là có chủ đích, cần công bố mốc migration, consumer phải nâng cấp, điều kiện rollback và khoảng thời gian hai phiên bản cùng tồn tại.

## 13. Kiểm thử ma trận phiên bản thay vì chỉ clean build

Với một API mới và implementation cũ, nên kiểm tra ít nhất các tổ hợp thực sự có thể xuất hiện:

| API runtime | Implementation binary | Caller | Mục tiêu |
|---|---|---|---|
| V1 | V1 | Caller V1 | Xác nhận baseline trước thay đổi |
| V2 | V1 | Caller V1 | Xem hành vi cũ có tiếp tục hoạt động không |
| V2 | V1 | Caller V2 gọi method mới | Phát hiện `AbstractMethodError` hoặc default conflict |
| V2 | V2 | Caller V2 | Xác nhận implementation mới hoạt động đúng |

Nếu có rollback mà API và implementation không triển khai đồng thời, cần bổ sung tổ hợp V1/V2 nếu hệ thống thực tế có thể tạo ra nó. Không phải mọi tổ hợp đều được hỗ trợ, nhưng giới hạn hỗ trợ phải được ghi rõ trong hợp đồng phát hành và tài liệu triển khai.

Các lớp kiểm thử phù hợp:

1. **Source compatibility:** biên dịch lại source implementation cũ với API mới để phát hiện thiếu abstract method hoặc default conflict.
2. **Binary compatibility:** chạy chính class file implementation/caller đã phát hành, không biên dịch lại, với API mới.
3. **Dispatch tests:** gọi trực tiếp các method mới, nhất là khi receiver là implementation cũ hoặc implement nhiều interface.
4. **Behavioral tests:** xác nhận default implementation, thứ tự chọn method và kết quả nghiệp vụ đúng kỳ vọng.
5. **Integration tests:** gọi qua dependency injection, proxy, reflection, plugin loader hoặc framework mà production thực sự sử dụng.
6. **Rollback tests:** xác nhận phiên bản cũ có thể hoạt động với dữ liệu và artifact còn tồn tại sau triển khai mới nếu đó là yêu cầu.

Công cụ so sánh API như japicmp hoặc Revapi hỗ trợ phát hiện thành viên mới, thay đổi modifier và khác biệt chữ ký, nhưng không đủ để kết luận toàn bộ hành vi chọn method trong ứng dụng thực tế. Vì vậy, kết quả API diff cần được kết hợp với test bằng **binary cũ** và đường gọi mới.

## 14. Những nhận định dễ sai

**“Thêm abstract method vào interface là binary-incompatible nên mọi class cũ sẽ lỗi khi load.”** Không chính xác. Binary cũ có thể tiếp tục được nạp và dùng method cũ; thiếu implementation thường bộc lộ khi method mới bị gọi.

**“Thêm abstract method là hoàn toàn an toàn vì đặc tả coi là binary-compatible.”** Cũng không chính xác. Nó có thể phá source compatibility và gây `AbstractMethodError` với caller mới + implementation cũ.

**“Có default method thì luôn an toàn.”** Không đúng. Hai default từ interface độc lập có thể xung đột; class method có thể được chọn với ngữ nghĩa khác; default implementation có thể sai nghiệp vụ.

**“Nếu khởi động ứng dụng không lỗi thì interface đã tương thích.”** Không đủ. Một số lỗi chỉ xuất hiện khi gọi method cụ thể, khi load plugin hoặc khi feature flag kích hoạt đường chạy hiếm.

**“Chỉ cần chạy test sau khi biên dịch lại toàn bộ project.”** Chưa đủ với hệ thống phát hành nhiều artifact độc lập. Biên dịch lại có thể phát hiện source error nhưng không tái hiện linkage failure của class file cũ trong production.

**“AbstractMethodError và NoSuchMethodError có cùng nguyên nhân.”** Không đúng. Một trường hợp thường là method được khai báo nhưng không có implementation concrete để gọi; trường hợp kia thường là lookup/resolution không còn tìm thấy member theo tên và descriptor mong đợi.

## 15. Checklist trước khi thêm method vào API

- [ ] Đã xác định interface/abstract class nào đang được công bố cho consumer.
- [ ] Đã liệt kê các implementation hiện tại, bao gồm plugin và binary do bên khác phát hành.
- [ ] Đã phân biệt abstract method mới với default method có implementation.
- [ ] Đã xác định source compatibility khi biên dịch lại implementation cũ.
- [ ] Đã xác định tình huống chạy binary cũ với API runtime mới.
- [ ] Đã tìm các method có cùng tên/descriptor trong class hierarchy và interface khác.
- [ ] Đã xem xét xung đột giữa hai default method độc lập.
- [ ] Đã xem xét functional interface và các lambda/method reference đang sử dụng.
- [ ] Đã kiểm tra thời điểm method mới thực sự được gọi, kể cả đường chạy hiếm.
- [ ] Đã chạy test bằng artifact/caller/implementation của các phiên bản cần hỗ trợ.
- [ ] Đã xác định hành vi mặc định và cách báo lỗi khi tính năng mới chưa được hỗ trợ.
- [ ] Đã ghi chính sách versioning, hướng dẫn migration và phương án rollback.

## 16. Kết luận

Thêm abstract method và thêm default method là hai cách mở rộng API có hệ quả khác nhau. **Abstract method mới** buộc implementation được biên dịch lại phải đáp ứng hợp đồng, nhưng binary implementation cũ có thể tiếp tục được nạp và chỉ phát sinh `AbstractMethodError` khi caller mới gọi method thiếu implementation. **Default method mới** có thể cung cấp hành vi cho binary cũ, nhưng có nguy cơ tạo xung đột giữa nhiều interface dẫn tới `IncompatibleClassChangeError` khi lời gọi cần chọn implementation.

Trong migration Java, kết luận tương thích phải nêu rõ API version, implementation binary version, caller version và phương thức được thực thi. Hãy kết hợp kiểm tra source, phân tích class file, kiểm thử binary cũ và kiểm thử các đường gọi thực tế để phát hiện lỗi đúng nơi chúng có thể xuất hiện.
