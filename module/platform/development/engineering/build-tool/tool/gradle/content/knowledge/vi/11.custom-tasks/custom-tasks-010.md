# Build Service dùng chung, vòng đời tài nguyên và giới hạn đồng thời

## 1. Mục tiêu và hoàn cảnh sử dụng

Trong một Gradle build có nhiều project và task, một số công việc cần dùng **cùng một tài nguyên đắt đỏ hoặc có giới hạn**: server kiểm thử, kết nối tới dịch vụ ngoài, HTTP client, bộ đệm kết quả tính toán, bộ cấp phát cổng, hoặc license chỉ cho phép một số phiên chạy đồng thời. Nếu mỗi task tạo và đóng tài nguyên riêng, build bị lãng phí thời gian khởi động và dễ xảy ra xung đột. Nếu lưu connection vào biến static hoặc biến của build script, Gradle khó quản lý vòng đời, task graph, configuration cache và việc thực thi song song.

**Shared Build Service** là đối tượng Gradle quản lý để nhiều task trong **cùng một build** chia sẻ trạng thái hoặc tài nguyên. Nó có ba năng lực chính:

1. **Đăng ký lười:** ghi nhận service nhưng chưa nhất thiết tạo instance khi cấu hình.
2. **Vòng đời có quản lý:** tạo instance khi cần; nếu service triển khai **AutoCloseable**, Gradle gọi **close()** khi không còn cần instance đó.
3. **Điều phối đồng thời:** property **maxParallelUsages** giới hạn số task được Gradle cho phép sử dụng service cùng lúc, nếu các task khai báo usage đúng cách.

Kết thúc bài học, bạn có thể viết service có hoặc không có parameters, dùng **gradle.sharedServices.registerIfAbsent**, nối service vào task qua **usesService** hoặc **@ServiceReference**, lựa chọn giới hạn phù hợp, xử lý thread-safety, kiểm chứng bằng ví dụ Java 17 và chẩn đoán lỗi ở CI.

## 2. Định nghĩa và phạm vi của Build Service

~~~text
                         MỘT GRADLE BUILD
+---------------------------------------------------------+
| gradle.sharedServices (BuildServiceRegistry)           |
|                                                         |
|   registerIfAbsent("gate", GateService, spec)            |
|                      |                                  |
|                      v                                  |
|               Provider<GateService>                     |
|                      |                                  |
|            +---------+----------+                       |
|            |                    |                       |
|            v                    v                       |
|      :app:useGate           :lib:useGate                 |
|       usesService             usesService                |
|            |                    |                       |
|            +---------+----------+                       |
|                      v                                  |
|               GateService instance                      |
|                   tạo khi cần                           |
|                      |                                  |
|                AutoCloseable.close()                    |
|                   khi hết nhu cầu                       |
+---------------------------------------------------------+
~~~

Phạm vi service là **một Gradle build**, không phải từng Project riêng. Các task thuộc subproject khác nhau có thể dùng một instance do registry của build cung cấp. Tuy nhiên, đừng mở rộng khái niệm thành singleton toàn hệ thống:

- Hai lần gọi **./gradlew** độc lập không chắc dùng chung service instance.
- Hai Gradle daemon hay hai CI runner không cùng một khóa tài nguyên chỉ vì có service trùng tên.
- Một composite build có những build độc lập; đừng coi registry của tất cả included build luôn là một registry.
- Khi dùng configuration cache, service instance sống không được lưu lại để tái sử dụng như một socket/connection xuyên lần build.

**BuildService<T extends BuildServiceParameters>** là giao diện service. Lớp triển khai thường là **abstract** để Gradle tạo managed instance. Nếu không có parameters thì dùng **BuildServiceParameters.None**. Nếu có parameters, định nghĩa một type implements **BuildServiceParameters** với các property có kiểu.

Build Service không tự đóng vai trò **task input**, **task dependency**, hệ thống chia sẻ file hay bộ điều khiển toàn bộ build. Những trách nhiệm đó vẫn cần khai báo qua task graph và input/output APIs.

## 3. Chọn trường hợp dùng phù hợp

| Nhu cầu | Có nên dùng Build Service? | Lưu ý |
| --- | --- | --- |
| Nhiều task cùng gọi một HTTP client | Có | Client phải thread-safe hoặc access được điều phối |
| Nhiều integration test cần một server tạm | Có | Start/stop trong lifecycle, timeout và cleanup |
| License chỉ cho một task trong build dùng | Có | maxParallelUsages=1 và mọi task phải khai báo usage |
| Cache kết quả tính toán trong memory | Có thể | Cache thread-safe; không được khiến task output sai |
| Task A tạo file, task B đọc file | Không thay Provider input/output | Dùng RegularFileProperty, @OutputFile, @InputFile |
| Task B phải chạy sau task A | Không thay dependsOn | Dùng dependency hoặc task output provider |
| Giới hạn số request trên toàn công ty | Không đủ | Cần quota/lock tại server, database hoặc hệ thống chung |
| Ghi kết quả triển khai production | Không làm việc đó trong close() | Sử dụng task riêng có trạng thái, output, lỗi rõ ràng |

Điểm mấu chốt: **Service giải quyết chia sẻ tài nguyên và phối hợp sử dụng**, còn **Task** giải quyết công việc và kết quả có thể kiểm chứng. Không nên làm Gradle bỏ qua input/output tracking chỉ vì hai task đã chia sẻ cùng một đối tượng.

## 4. Định nghĩa một Build Service

### 4.1. Trường hợp không cần tham số

Ví dụ class Java minh họa:

~~~java
import org.gradle.api.services.BuildService;
import org.gradle.api.services.BuildServiceParameters;

public abstract class LabelService
        implements BuildService<BuildServiceParameters.None>, AutoCloseable {

    public String decorate(String text) {
        return "SERVICE: " + text;
    }

    @Override
    public void close() {
        System.out.println("SERVICE CLOSED");
    }
}
~~~

Đây là **một lớp minh họa**, chưa phải file project chạy độc lập. Để dùng trong build, đặt nó trong một plugin hoặc **buildSrc**; nếu có package thì thư mục và import phải khớp. Không tự triển khai **getParameters()**: Gradle sẽ cung cấp implementation thích hợp.

**AutoCloseable** là tùy chọn. Nếu không giữ tài nguyên cần giải phóng, không bắt buộc triển khai close. Với client/server/file handle, nên triển khai close để gọi API đóng của tài nguyên. Tránh đặt nhiệm vụ tạo artifact hoặc publish trong **close()** vì nó không phải một task có output/lỗi được tracking bình thường.

### 4.2. Service có parameters

Thường cần host, port, tên môi trường hoặc timeout. Dùng một type có getter theo JavaBeans convention:

~~~java
package example.build;

import org.gradle.api.provider.Property;
import org.gradle.api.services.BuildService;
import org.gradle.api.services.BuildServiceParameters;

public abstract class PrefixService
        implements BuildService<PrefixService.Params> {

    public interface Params extends BuildServiceParameters {
        Property<String> getPrefix();
    }

    public String decorate(String text) {
        return getParameters().getPrefix().get() + text;
    }
}
~~~

Trong một build script có class **PrefixService** trên classpath:

~~~groovy
import example.build.PrefixService

def serviceProvider = gradle.sharedServices.registerIfAbsent(
    'prefixService',
    PrefixService
) {
    parameters.prefix.set('Report: ')
}
~~~

Các điểm quan trọng:

- **getPrefix()** là getter mà Gradle quản lý, tương ứng **parameters.prefix** trong Groovy DSL. Không định nghĩa method tùy ý **prefix()** thay thế rồi chờ Gradle tự nhận dạng.
- Giá trị nên ổn định và có kiểu. Nếu chứa URL, port hoặc đường dẫn, hãy cấu hình qua Provider/Property thích hợp.
- **getParameters()** do Gradle tạo; không tự thực hiện ở service.
- **maxParallelUsages** không phải tham số nghiệp vụ của **Params**. Nó là property trên **BuildServiceSpec**.
- Secret không nên nhúng vào script được commit hoặc in trong log; dùng cơ chế cung cấp bí mật thích hợp và bảo vệ quyền truy cập.

## 5. registerIfAbsent và Provider

Đăng ký service có cú pháp Groovy DSL:

~~~groovy
def gateProvider = gradle.sharedServices.registerIfAbsent(
    'sharedGate',
    GateService
) {
    maxParallelUsages.set(1)
}
~~~

**GateService** trong đoạn này là class đã có trong build logic, không phải built-in class. **registerIfAbsent** dùng tên registration để trả **Provider** tương ứng nếu đã đăng ký, hoặc đăng ký mới nếu chưa có. Nó không đồng nghĩa tạo object GateService ngay tại thời điểm đọc **build.gradle**.

Với một service đã tồn tại, registration có thể **không chạy lại configuration action** của lần gọi tiếp theo. Vì thế mọi nơi gọi cùng tên phải thống nhất kiểu, parameters và giới hạn; tốt hơn nữa là đưa logic đăng ký vào plugin/convention thống nhất.

**Không chủ động gọi gateProvider.get() ở top-level build.gradle** chỉ để xem service có được tạo không. Điều này có thể khởi tạo tài nguyên sớm, gây side effect ở configuration và làm phức tạp configuration cache. Nên giữ Provider và chỉ lấy instance khi task thực sự sử dụng.

## 6. Hai cách nối task với service và giới hạn đồng thời

### 6.1. @Internal + set(provider) + usesService

Với custom task khai báo property:

~~~java
@Internal
public abstract Property<GateService> getGate();
~~~

Khi cấu hình task:

~~~groovy
tasks.register('workWithGate', UseGateTask) {
    gate.set(gateProvider)
    usesService(gateProvider)
}
~~~

Hai đoạn trên là **minh họa API**, yêu cầu đã định nghĩa **GateService**, **UseGateTask**, **gateProvider** và import annotation. Cách này có **hai bước bắt buộc**:

1. **gate.set(gateProvider)** nối provider vào property của task để task lấy được service.
2. **usesService(gateProvider)** khai báo cho scheduler biết task chiếm slot của service. Nhờ đó **maxParallelUsages** được áp dụng.

Đánh dấu **@Internal** vì instance service không phải input nghiệp vụ mà Gradle nên hash như một giá trị input. Những input thực cần được khai báo riêng bằng **@Input**, **@InputFile**, **@InputFiles**.

Với task kiểu mặc định và doLast closure, có thể dùng trực tiếp:

~~~groovy
def shared = gradle.sharedServices.registerIfAbsent('gate', GateService) {
    maxParallelUsages.set(1)
}

tasks.register('myWork') {
    usesService(shared)
    doLast {
        shared.get().runWork('myWork')
    }
}
~~~

Cũng là **đoạn minh họa**, trong đó **GateService** cần có method **runWork(String)**. Quy tắc là **khai báo usesService**, không chỉ giữ một biến provider.

### 6.2. @ServiceReference

Một custom task hiện đại có thể khai báo:

~~~java
@ServiceReference("sharedGate")
public abstract Property<GateService> getGate();
~~~

Với registration **sharedGate** cùng type, Gradle có thể tự inject provider và tự nhận diện task usage. Ở trường hợp này, không cần gọi riêng **usesService** chỉ để Gradle biết task đó sử dụng service. Nếu cùng type tồn tại dưới nhiều tên, hãy chỉ rõ tên hoặc cung cấp provider tường minh tránh ambiguity.

Không kết hợp **@Internal** và **@ServiceReference** trên một property. Không đánh dấu service bằng một annotation input khác rồi chờ Gradle hiểu: service property được hỗ trợ qua **@ServiceReference** hoặc **@Internal**.

### 6.3. Sử dụng gián tiếp không được Gradle tự phát hiện hoàn toàn

Nếu task chỉ khai báo service A, nhưng service A gọi service B, scheduler có thể không biết task cũng đang chiếm service B. Khi B cần limit, hãy khai báo usage của B **trực tiếp** trên task bằng **usesService(B)** hoặc **@ServiceReference** phù hợp.

Điều này lý giải tình huống **maxParallelUsages=1 nhưng các task vẫn tranh chấp tài nguyên**: không phải cứ có property trong registration là mọi tác vụ gọi tài nguyên sẽ được điều phối.

## 7. Vòng đời: đăng ký, khởi tạo, sử dụng và đóng

~~~text
CONFIGURATION
  registerIfAbsent("gate", GateService)
       |
       v
  Provider<GateService> được nối vào tasks
       |
       v
EXECUTION
  Một task thực sự yêu cầu service
       |
       v
  Gradle tạo instance khi cần
       |
       v
  Task sử dụng instance; task khác có thể dùng cùng instance
       |
       v
  Tất cả task sử dụng đã kết thúc
       |
       v
  Gradle giải phóng instance khi không cần
       |
       v
  AutoCloseable.close() nếu service triển khai
~~~

**Không có task nào cần service thì registration có thể không bao giờ tạo instance**, nên constructor và close không chạy. Một task có trong graph nhưng không thực sự truy cập instance cũng không nhất thiết kích hoạt việc khởi tạo tài nguyên.

Gradle gọi **close()** trong khoảng thời gian từ sau task cuối cùng sử dụng service đến khi build kết thúc; đừng dựa vào một vị trí log tuyệt đối của close. Sử dụng **try/finally** để trả tài nguyên sau từng lần dùng và **close()** để đóng tài nguyên thuộc cả service.

### 7.1. Cleanup khi có lỗi

Nếu action của một task ném exception, service vẫn phải được thiết kế để không giữ một lock hoặc session bị treo. Với build kết thúc bình thường ở cấp Gradle dù task thất bại, Gradle có thể dọn service mà nó đã tạo. Tuy nhiên, khi JVM crash, process bị kill cứng hoặc máy mất điện, không thể bảo đảm close chạy. Tài nguyên bên ngoài như license/DB lock nên có **lease/timeout/cleanup dự phòng**.

### 7.2. Configuration cache

Với configuration cache, Gradle lưu cấu hình/parameters cần thiết, **không đóng băng một socket, HTTP client hay service instance sống** qua lần build sau. Service được tạo lại khi cần. Nếu gọi provider.get() ngay ở configuration, instance có thể được tạo và dọn sau phase cấu hình, rồi tạo lại ở execution; tránh giả định constructor chỉ chạy đúng một lần trong mọi trường hợp.

Hãy **đăng ký trong configuration, sử dụng trong task action**, và kiểm tra tài liệu configuration cache trước khi đưa state/callback phức tạp vào service.

## 8. maxParallelUsages điều phối task, không điều phối từng thread

Khi đăng ký:

~~~groovy
maxParallelUsages.set(1)
~~~

Gradle cho phép **tối đa một task có khai báo sử dụng service** dùng nó tại một thời điểm. Với giá trị **2**, tối đa hai task. Nếu property không có giá trị, Gradle không đặt giới hạn task-use riêng cho service. Giá trị khi đặt phải là số nguyên dương.

| Cấu hình | Ý nghĩa |
| --- | --- |
| **maxParallelUsages=1** | Không hơn một task sử dụng cùng service đồng thời |
| **maxParallelUsages=2** | Không hơn hai task sử dụng cùng service đồng thời |
| Không thiết lập | Không áp trần riêng theo service |
| **--max-workers=4** | Giới hạn worker tổng quát của Gradle, khác giới hạn từng service |
| **--parallel** | Cho phép Gradle lập lịch những task đủ điều kiện song song, không bỏ qua service limit |

Giới hạn **không** nói rằng tất cả task trong build phải chạy tuần tự. Các task không dùng service vẫn có thể chạy song song theo scheduler. Nó cũng không nói một task dùng service chỉ tạo một thread hoặc một request: nếu task tự tạo 20 thread, cần cơ chế đồng bộ nội bộ để giới hạn số kết nối thực.

**Một Build Service phải thread-safe** vì có thể được dùng từ nhiều task, Worker API hoặc thread bên trong task, hay limit có thể được tăng về sau. Thread-safety không nên dựa hoàn toàn vào cấu hình maxParallelUsages.

Giới hạn này không có hiệu lực toàn tổ chức: hai build độc lập cùng limit 1 vẫn có thể đồng thời đánh vào một server. Với giới hạn toàn hệ thống, dùng khóa/distributed semaphore/quota ở dịch vụ chung.

## 9. Ví dụ chạy được: Java 17 và hai subproject dùng cùng Build Service

Ví dụ dưới đây chạy với Gradle tương thích JDK 17+, gồm hai module **:app** và **:lib**, cùng đăng ký service tên **sharedGate** trong một build. Class service nằm trong **buildSrc**, dùng một **AtomicInteger** theo dõi số lần sử dụng hiện tại. Hai task đặt **usesService(gate)** và limit 1. Ta dùng Thread.sleep(250) chỉ để quan sát overlap; không dùng sleep như kỹ thuật đồng bộ trong sản phẩm.

### 9.1. Cấu trúc

~~~text
shared-service-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── buildSrc/
│   ├── build.gradle
│   └── src/main/java/demo/build/SharedGate.java
├── app/
│   ├── build.gradle
│   └── src/main/java/demo/App.java
└── lib/
    └── build.gradle
~~~

Các file Wrapper được sinh bằng **gradle wrapper** ở máy có Gradle CLI đáng tin, sau đó dùng **./gradlew** hoặc **.\gradlew.bat** trong repo. **buildSrc** là build logic của Gradle, không phải module ứng dụng trong include.

### 9.2. settings.gradle

~~~groovy
rootProject.name = 'shared-service-lab'
include ':app', ':lib'
~~~

### 9.3. buildSrc/build.gradle

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation gradleApi()
}
~~~

**gradleApi()** cung cấp Gradle API để biên dịch class service. **buildSrc** được biên dịch trước khi các build script chính cần đến **SharedGate**. JDK chạy Gradle phải tương thích; app Java dùng toolchain 17.

### 9.4. buildSrc/src/main/java/demo/build/SharedGate.java

~~~java
package demo.build;

import java.util.concurrent.atomic.AtomicInteger;
import org.gradle.api.services.BuildService;
import org.gradle.api.services.BuildServiceParameters;

public abstract class SharedGate
        implements BuildService<BuildServiceParameters.None>, AutoCloseable {

    private final AtomicInteger active = new AtomicInteger();

    public void use(String label) {
        int now = active.incrementAndGet();
        try {
            System.out.println("START " + label + " active=" + now);
            Thread.sleep(250);
            System.out.println("END " + label);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted: " + label, ex);
        } finally {
            active.decrementAndGet();
        }
    }

    @Override
    public void close() {
        System.out.println("CLOSE sharedGate");
    }
}
~~~

**AtomicInteger** đảm bảo thao tác tăng/giảm **active** không có data race. **finally** giảm biến ngay cả khi task bị interrupt. **close()** được Gradle gọi khi instance không còn cần; ở dự án thật nó đóng resource (database connection, server, client), không chỉ println. **Thread.sleep** mô phỏng công việc chứ không quyết định chính sách song song.

### 9.5. build.gradle ở root

~~~groovy
plugins {
    id 'base'
}

tasks.register('runAll') {
    group = 'verification'
    description = 'Chạy hai task dùng service chung'
    dependsOn ':app:useGate', ':lib:useGate'
}
~~~

**runAll** chỉ khai báo hai dependency. Nó không tự dùng service và không cần chiếm slot.

### 9.6. app/build.gradle

~~~groovy
import demo.build.SharedGate

plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.App'
}

def gate = gradle.sharedServices.registerIfAbsent('sharedGate', SharedGate) {
    maxParallelUsages.set(1)
}

tasks.register('useGate') {
    group = 'verification'
    usesService(gate)

    doLast {
        gate.get().use('app')
    }
}
~~~

Application plugin tạo task **run**. Task **useGate** là task riêng, có provider, khai báo **usesService(gate)** và lấy instance trong doLast chứ không ở configuration.

### 9.7. lib/build.gradle

~~~groovy
import demo.build.SharedGate

plugins {
    id 'base'
}

def gate = gradle.sharedServices.registerIfAbsent('sharedGate', SharedGate) {
    maxParallelUsages.set(1)
}

tasks.register('useGate') {
    group = 'verification'
    usesService(gate)

    doLast {
        gate.get().use('lib')
    }
}
~~~

Cả hai script dùng **cùng tên registration và implementation class** thuộc cùng Gradle build. **registerIfAbsent** không tạo một service riêng cho từng project. Để không phụ thuộc thứ tự đăng ký, cả hai chỗ đặt cùng limit 1. Trong sản phẩm, nên đăng ký thống nhất qua convention plugin thay vì nhân bản đoạn script này.

### 9.8. app/src/main/java/demo/App.java

~~~java
package demo;

public final class App {
    private record Greeting(String name) {
    }

    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Java 17 OK: " + new Greeting("Gradle").name());
    }
}
~~~

**record** được Java 17 hỗ trợ. Đường dẫn, package và tên class phải khớp đúng như trên. Chương trình chỉ dùng Java standard library.

### 9.9. Các lệnh chạy

Linux/macOS:

~~~bash
./gradlew --version
./gradlew --parallel --max-workers=4 runAll
./gradlew :app:run
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat --parallel --max-workers=4 runAll
.\gradlew.bat :app:run
~~~

Các dòng do service in khi chạy **runAll** có thể xuất hiện theo thứ tự dưới đây:

~~~text
START app active=1
END app
START lib active=1
END lib
CLOSE sharedGate
~~~

Thứ tự **app/lib không cố định**: scheduler có thể chạy lib trước app. Điều cần kiểm tra là không có khoảng **START–END** chồng nhau khi maxParallelUsages=1, và **active=1** cho từng lần dùng. Vị trí dòng **CLOSE** phụ thuộc lúc Gradle giải phóng service sau khi task cuối kết thúc.

Dòng stdout **chính xác của chương trình Java** khi gọi **:app:run**:

~~~text
Java 17 OK: Gradle
~~~

Gradle có thể in thêm task log và trạng thái build. Chỉ gọi **:app:run** không cần kích hoạt service, vì task Java không được cấu hình dùng gate.

### 9.10. Chạy Java bằng javac để kiểm tra riêng source

Linux/macOS:

~~~bash
mkdir -p out
javac --release 17 -d out app/src/main/java/demo/App.java
java -cp out demo.App
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out
javac --release 17 -d out app\src\main\java\demo\App.java
java -cp out demo.App
~~~

Kết quả:

~~~text
Java 17 OK: Gradle
~~~

Lệnh javac xác minh Java source; chỉ các lệnh Gradle **runAll** mới kiểm tra Build Service, task scheduling và giới hạn đồng thời.

## 10. Thử thay đổi giới hạn và quan sát

**Trường hợp A — giữ limit=1:** Chạy **runAll --parallel --max-workers=4**. Kỳ vọng các task đã khai báo usage không được scheduler cho dùng đồng thời quá một task.

**Trường hợp B — đổi limit=2:** Thay **maxParallelUsages.set(1)** bằng **maxParallelUsages.set(2)** ở **cả hai module** rồi chạy lại. Có thể thấy **START app active=1** và **START lib active=2** trước một dòng END, nếu scheduler cho hai task chạy đồng thời. Tuy nhiên không thấy overlap trong một lượt chạy cũng không chứng minh Gradle sai: concurrency là cơ hội, không phải yêu cầu bắt buộc.

**Trường hợp C — cố ý bỏ usesService:** Tạm xóa dòng **usesService(gate)** ở một module, nhưng để lời gọi **gate.get()**. Giới hạn service không còn được khai báo đầy đủ với scheduler. Có thể gặp overlap dù limit=1, tùy scheduling. Cần khôi phục dòng usage ngay sau thử nghiệm. Đừng biến bài test này thành config production.

**Trường hợp D — không kích hoạt service:** Chỉ chạy **:app:run**. Vì task này không lấy service, provider có thể không cần tạo instance, nên dòng **CLOSE sharedGate** không xuất hiện. Đó không phải lỗi.

**Trường hợp E — task ném lỗi:** Trong method use, thử ném IllegalStateException có chủ đích trước khi kết thúc, vẫn giữ finally. Task phải FAILED; bộ đếm vẫn được trả về trạng thái đúng, và Gradle cố gắng dọn service nếu tiến trình còn hoạt động bình thường. Đừng đưa lỗi thử nghiệm vào CI phát hành.

## 11. Vấn đề thread-safety và mô hình tài nguyên

### 11.1. Mutable state không được bảo vệ

Ví dụ sai trong một service dùng chung:

~~~java
private int count;

public void increment() {
    count++;
}
~~~

Hai thread cùng tăng biến có thể mất cập nhật. Thay bằng:

~~~java
private final java.util.concurrent.atomic.AtomicInteger count =
        new java.util.concurrent.atomic.AtomicInteger();

public int increment() {
    return count.incrementAndGet();
}
~~~

AtomicInteger chỉ bảo vệ phép cập nhật trên biến đó. Khi một bất biến gồm nhiều field, một map, connection pool hoặc transaction, cần synchronized lock, concurrent collection, immutable state hoặc giao thức phù hợp. **maxParallelUsages không tự bảo vệ mọi thread của một task**.

### 11.2. Chỉ giới hạn task chưa chắc giới hạn tài nguyên thực

Nếu một task dùng service rồi tạo 10 work action đồng thời, scheduler xem đó là **một task sử dụng service**, không phải 10 slot tự động. Vì vậy cần thiết kế **Semaphore**, connection pool hoặc rate limiter bên trong service khi tài nguyên thực có giới hạn theo thread/request.

Với tài nguyên chịu giám sát toàn hệ thống, đặt hạn mức tại server/client chung. Hai Gradle build khác nhau có thể cùng maxParallelUsages=1 và vẫn truy cập một DB cùng lúc.

### 11.3. Producer–consumer không thể thay bằng Shared Build Service

Ví dụ task A sinh **build/generated/data.json**, task B cần file đó. Dùng file output Provider và input của task để Gradle biết B phụ thuộc A. Đừng đặt dữ liệu file vào field service rồi hy vọng Gradle suy ra dependency.

~~~text
Task producer
  |
  +-- @OutputFile / Provider<RegularFile>
                   |
                   v
Task consumer -- @InputFile
~~~

**dependsOn(taskProvider)** hoặc wiring output Provider biểu diễn thứ tự nghiệp vụ, còn **maxParallelUsages** chỉ điều phối mức sử dụng chung. Hai khái niệm độc lập; có thể cần cả hai.

### 11.4. Không coi state của service là task input tự động

Nếu output của task thay đổi theo một field mutable của service mà Gradle không biết, up-to-date checks và build cache có thể trả kết quả cũ sai. Khai báo input/output thực qua **@Input**, **@InputFile**, **@OutputFile** và Property/Provider phù hợp. Nếu task thực sự không thể cache đúng, cấu hình chính sách caching có chủ đích thay vì để Gradle đoán từ service.

## 12. Lỗi, cleanup và configuration cache

Một task có thể ném GradleException khi API ngoài bị lỗi. Không catch rồi in “SUCCESS” một cách giả tạo. Dùng try/finally để giải phóng session ở mức từng lần gọi và **AutoCloseable.close()** để đóng tài nguyên sống theo vòng đời service.

**Không bảo đảm close() khi process bị kill cứng.** Với database transaction hoặc server ngoài, thiết kế timeout, lease, idempotency và cleanup dự phòng.

Khi bật configuration cache:

~~~bash
./gradlew --configuration-cache runAll
./gradlew --configuration-cache runAll
~~~

Gradle có thể lưu lại thông tin configuration khi tương thích, nhưng **service instance không tồn tại xuyên các lần build**; mỗi lần thực sự cần service sẽ tạo instance mới. Không lưu Project/Task object hoặc mutable script state vào service như cách né yêu cầu của configuration cache.

Đối với Worker API, Build Service có thể được truyền qua Provider đến work action ở những isolation mode được hỗ trợ. Tài liệu Gradle hiện hành có giới hạn đối với classloader/process isolation trong các ví dụ sử dụng service; cần kiểm tra tài liệu của phiên bản thực tế. Không mặc định một task launch nhiều worker sẽ được scheduler tính thành nhiều service usage slot.

Đối với giám sát task events, có thể dùng Build Service triển khai **OperationCompletionListener** kết hợp **BuildEventsListenerRegistry.onTaskCompletion(provider)**. Đây là vai trò khác với service điều phối license/client; không trộn các trách nhiệm không liên quan vào cùng một service khi logic và giới hạn khác nhau.

## 13. Bảng chẩn đoán nhanh

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Có registration nhưng không thấy instance/close | Không task nào thực sự lấy service | Kiểm tra task graph, provider.get, @ServiceReference |
| Service khởi tạo ngay khi chạy help | Đọc provider ở top-level configuration | Giữ Provider lazy, dùng ở task action |
| Limit=1 nhưng task vẫn tranh chấp | Thiếu usesService, @ServiceReference hoặc usage gián tiếp | Khai báo usage trực tiếp với Gradle |
| Limit=2 nhưng task chạy tuần tự | Scheduler/worker count/graph không có parallelism | Thử task hai subproject, dùng --parallel --max-workers |
| Nhiều project tạo instance khác nhau | Tên registration, type hoặc build registry khác | Chuẩn hóa tên/type, xác định đúng build scope |
| registerIfAbsent ở hai module có settings khác nhau | Registration đầu tiên quyết định cấu hình ban đầu | Tập trung policy ở plugin, không cấu hình mâu thuẫn |
| close không chạy khi hard kill | JVM bị chấm dứt bất thường | Timeout/lease/cleanup ngoài Gradle |
| Service tạo lại khi dùng configuration cache | Instance không được cache; có thể eager-get ở configuration | Không giữ kỳ vọng instance xuyên build |
| @ServiceReference không được inject | Tên/type không khớp, registration thiếu | Kiểm tra annotation, registry và provider |
| Task B đọc file chưa tạo từ task A | Thiếu input/output wiring hoặc task dependency | Dùng Provider<RegularFile>, dependsOn khi cần |
| Task UP-TO-DATE nhưng dữ liệu service đã đổi | State service chưa được khai báo như task input | Khai báo input nghiệp vụ tường minh |
| Có race trong map hoặc counter | Mutable state không thread-safe | Atomic/concurrent collection/lock |
| CI mất license dù limit=1 | Có nhiều build/runner độc lập | Dùng điều phối ở server/license system |
| Build treo | Connection/lock không nhả hoặc request thiếu timeout | try/finally, timeout, log chẩn đoán |

## 14. Quy trình tự kiểm tra và thực hành

Khi nghi Build Service hoạt động sai, hỏi theo thứ tự:

1. Đã dùng đúng Gradle Wrapper và đúng build root chưa?
2. **registerIfAbsent** có cùng name/type ở các project không?
3. Task cần kiểm tra có nằm trong graph không?
4. Task có gọi service lúc execution, hay service đã bị tạo sớm ở configuration?
5. Task dùng **@ServiceReference**, hay dùng **@Internal + set(provider) + usesService(provider)**?
6. **maxParallelUsages** là số nguyên dương và được thiết lập nhất quán chưa?
7. Có đủ task song song thực sự để kiểm tra limit không?
8. Logic bên trong service có thread-safe và try/finally không?
9. Vòng đời close được quan sát trong điều kiện nào, có configuration cache/hard kill không?
10. Input/output của task đã rõ, có đang lạm dụng service để chia sẻ file không?

Các lệnh hữu ích:

~~~bash
./gradlew --version
./gradlew tasks --all
./gradlew --parallel --max-workers=4 runAll --info
./gradlew runAll --stacktrace
./gradlew --configuration-cache runAll
~~~

**runAll** là tên task ví dụ ở mục 9, không tự có trong mọi Gradle build. Log dưới **--info** có thể giúp phân biệt cấu hình, task execution và lỗi khởi tạo service; không nhất thiết có đúng thứ tự in log giữa các module.

## 15. Câu hỏi củng cố

1. Build Service được chia sẻ trong phạm vi nào, và vì sao không dùng nó để khóa giữa hai CI runner?
2. Vì sao registerIfAbsent trả Provider chứ không nhất thiết khởi tạo service ngay?
3. Khi custom task đánh dấu property service bằng **@Internal**, cần đủ những bước nào?
4. Khi dùng **@ServiceReference("sharedGate")**, Gradle tự làm gì?
5. maxParallelUsages=1 có khiến mọi task trong build tuần tự không?
6. Tại sao một task tạo 20 thread vẫn có thể gây quá tải server khi limit=1?
7. Vì sao AutoCloseable.close() không phải một task publish hoặc callback cuối build luôn chạy?
8. Nếu service không bao giờ được dùng, có bắt buộc xuất hiện log close không?
9. Build Service có được giữ sống giữa hai lần configuration cache hit không?
10. Vì sao cần AtomicInteger hoặc đồng bộ dù đã dùng maxParallelUsages?
11. Nếu task A tạo file cho task B, nên dùng Provider input/output hay Build Service state?
12. Nếu hai module gọi registerIfAbsent cùng name nhưng khác limit, điều gì đáng lo?

**Đáp án:** (1) một Gradle build, không khóa liên tiến trình/máy; (2) registration lazy; (3) nối provider vào property và usesService; (4) inject đúng service theo tên/type và nhận diện usage; (5) không, chỉ task dùng service; (6) cap đếm task không đếm thread/request; (7) phụ thuộc service được tạo và lifecycle Gradle, không thay task có input/output; (8) không; (9) không, instance được tạo mới; (10) service có thể được dùng từ nhiều thread và giới hạn có thể thay đổi; (11) input/output Provider và dependency; (12) registration đầu tiên quyết định cấu hình, nên nhất quán hoặc tập trung policy.

## 16. Checklist áp dụng và tài liệu chính thức

Trước khi merge code dùng Build Service:

- Xác định tài nguyên chia sẻ thật sự, giới hạn thực và phạm vi **một build**.
- Đặt tên service ổn định, class/parameters nhất quán giữa các module.
- Đăng ký lazily qua **gradle.sharedServices.registerIfAbsent**.
- Khai báo usage chính xác bằng **usesService** hoặc **@ServiceReference**.
- Chọn **maxParallelUsages** theo task-level capacity, không nhầm với số connection nội bộ.
- Đảm bảo service thread-safe, có cleanup và timeout khi quản lý tài nguyên ngoài.
- Khai báo đầy đủ task input/output, không dùng service thay dependency graph.
- Thử khi bật **--parallel** và **configuration cache**, kiểm tra cả trường hợp lỗi.
- Không đưa credential vào mã nguồn hoặc log; giữ quality gate của CI chính xác.

Tài liệu tham khảo:

- [Gradle — Using Shared Build Services](https://docs.gradle.org/current/userguide/build_services.html)
- [Gradle — BuildService API](https://docs.gradle.org/current/javadoc/org/gradle/api/services/BuildService.html)
- [Gradle — BuildServiceSpec: maxParallelUsages](https://docs.gradle.org/current/javadoc/org/gradle/api/services/BuildServiceSpec.html)
- [Gradle — BuildServiceRegistry](https://docs.gradle.org/current/javadoc/org/gradle/api/services/BuildServiceRegistry.html)
- [Gradle — Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html)
- [Gradle — Sharing Build Logic with buildSrc](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html)
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html)

**Kết luận:** Build Service giúp Gradle chia sẻ một tài nguyên có vòng đời quản lý và điều phối số task sử dụng đồng thời. Ba điều quyết định tính đúng đắn là **khai báo usage cho scheduler**, **thiết kế service thread-safe/cleanup được** và **giữ input/output của task rõ ràng**. Khi áp dụng đúng, build đa module có thể sử dụng chung server, client hoặc license một cách kiểm soát mà không hy sinh tính đúng đắn của task graph, caching hay CI.
