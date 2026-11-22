# Biến đổi giá trị bằng map, flatMap và kết hợp Provider trong Gradle

## Mục tiêu bài học

Một giá trị cấu hình Gradle có thể chỉ được biết khi đọc Gradle property, biến môi trường hoặc đầu ra của task khác. Nếu lấy giá trị đó quá sớm bằng **get()**, build dễ mất tính lười (lazy), tạo lỗi thứ tự cấu hình hoặc làm Gradle không theo dõi được quan hệ task. **Provider** giúp biểu diễn một giá trị *có thể chưa sẵn sàng*, còn **map**, **flatMap** và **zip** giúp tạo những giá trị dẫn xuất mà chưa buộc chúng phải được tính ngay.

Sau bài này bạn có thể:

1. Phân biệt **Provider<T>** (nguồn giá trị để đọc) với **Property<T>** (giá trị có thể cấu hình và cũng là Provider).
2. Dùng **map** để biến một giá trị **T → R** mà vẫn nhận về **Provider<R>**.
3. Dùng **flatMap** khi hàm biến đổi trả về **Provider<R>**, chẳng hạn chọn nguồn cấu hình theo một giá trị khác hoặc nối output của task.
4. Dùng **zip** để kết hợp hai Provider và nối nhiều phép kết hợp theo chuỗi.
5. Hiểu trường hợp **Provider không có giá trị**, **orElse**, **getOrElse**, **isPresent** và quy tắc xử lý null.
6. Truyền Provider vào **Property.set(provider)** hoặc input của task để Gradle duy trì phép tính lazy và task dependencies.
7. Nhận biết lỗi như gọi **get()** ở configuration phase, tạo **Provider<Provider<T>>**, bỏ lỡ dependency của producer, hoặc gây tác dụng phụ trong transformer.

Bài dùng **Gradle Groovy DSL** trong **build.gradle** làm ví dụ chính; có bảng đối chiếu **Kotlin DSL** ở cuối. Những câu lệnh mẫu được thực hiện trong dự án Gradle có Wrapper đáng tin cậy.

## 1. Nhắc lại: Provider là gì và vì sao cần biến đổi giá trị?

**Provider<T>** mô tả một giá trị kiểu T mà Gradle có thể tính hoặc cung cấp theo yêu cầu. Có Provider luôn có giá trị; có Provider có thể **absent** nếu nguồn chưa tồn tại. Provider cũng có thể mang **thông tin dependency của task** đã tạo ra giá trị ấy.

Ví dụ một Gradle property được truyền bằng **-Pservice=orders**:

~~~groovy
def service = providers.gradleProperty('service')
~~~

Ở dòng này **service** có kiểu ý nghĩa **Provider<String>**. Nó chưa phải chuỗi **"orders"**. Nếu gọi **service.get()**, bạn yêu cầu lấy giá trị ngay, và thao tác sẽ thất bại nếu property **service** không có.

Cách cung cấp mặc định mà vẫn giữ Provider:

~~~groovy
def service = providers.gradleProperty('service').orElse('orders')
~~~

**orElse('orders')** trả về **một Provider mới**, lấy giá trị gốc nếu có; nếu gốc không có thì dùng chuỗi **orders**. Nó không phải câu lệnh lấy giá trị ngay.

Có hai loại API thường gặp:

| Kiểu/API | Vai trò | Ví dụ |
| --- | --- | --- |
| **Provider<T>** | Giá trị được đọc/biến đổi; không có API thay giá trị qua **set** | **providers.gradleProperty('service')** |
| **Property<T>** | Provider có thể cấu hình bằng **set**, **convention** và các quy tắc hoàn tất | **objects.property(String)** |
| **RegularFileProperty** | Property cho đường dẫn file theo mô hình Gradle | **objects.fileProperty()** |
| **DirectoryProperty** | Property cho thư mục theo mô hình Gradle | **objects.directoryProperty()** |
| **TaskProvider<T>** | Đại diện cho Task được đăng ký lazy | **tasks.register('generate')** |

Bạn có thể đặt Provider thành nguồn của Property:

~~~groovy
def endpoint = objects.property(String)
def source = providers.gradleProperty('endpoint').orElse('http://localhost')

endpoint.set(source)
~~~

Đây là **kết nối lười**: endpoint phụ thuộc source, thay vì đọc source rồi sao chép một chuỗi ngay trong configuration phase.

### 1.1. Một sơ đồ về dòng dữ liệu

~~~text
Provider<String>  ── map(T -> R) ──> Provider<R>
       |
       └──────── flatMap(T -> Provider<R>) ──> Provider<R>

Provider<A> ─┐
             ├─ zip((A, B) -> R) ──> Provider<R>
Provider<B> ─┘
~~~

**map** tạo giá trị mới; **flatMap** chuyển tới một Provider mới; **zip** kết hợp hai nguồn. Cả ba đều tạo ra Provider có thể tiếp tục kết hợp hoặc gắn vào task input.

**Lazy không có nghĩa transformer bắt buộc chỉ chạy đúng một lần.** Gradle có thể truy vấn Provider nhiều lần, hoặc cấu hình cache có thể materialize một phần chuỗi tính toán. Transformer nên là hàm **thuần**, không ghi file, không chạy lệnh ngoài và không thay đổi global state.

## 2. map: biến đổi giá trị thường mà chưa lấy giá trị ngay

**Chữ ký về mặt ý tưởng:**

~~~text
Provider<T>.map(T -> R) : Provider<R>
~~~

Ví dụ từ **service** là chuỗi thành chữ in hoa:

~~~groovy
def service = providers.gradleProperty('service').orElse('orders')
def upperService = service.map { value ->
    value.toUpperCase()
}
~~~

Ở đây:

- **service**: **Provider<String>**.
- Closure nhận **String** khi nguồn được truy vấn.
- **value.toUpperCase()** trả về **String**, không phải Provider.
- **upperService**: **Provider<String>**, giá trị dự kiến là **ORDERS** nếu không truyền **-Pservice**.

Có thể nối **map** để thực hiện nhiều bước:

~~~groovy
def cleanService = service
    .map { it.trim() }
    .map { it.toLowerCase() }
    .map { it.replace(' ', '-') }
~~~

Với **-Pservice="Order API"**, phép tính logic là:

~~~text
"Order API" -> "Order API" -> "order api" -> "order-api"
~~~

Các closure này chỉ được sử dụng khi Gradle cần giá trị từ Provider dẫn xuất; tạo chuỗi **map** không có nghĩa chuỗi đã được tính tại dòng khai báo.

**Lưu ý về kiểu:** **Provider.map** không biến đổi kiểu tĩnh của nguồn ban đầu; nó trả về **Provider mới**. Nếu muốn lấy Integer từ String:

~~~groovy
def portText = providers.gradleProperty('port').orElse('8080')
def portNumber = portText.map { it.toInteger() }
~~~

**portNumber** là Provider của giá trị số nguyên **8080** khi nguồn hợp lệ. Nếu truyền **-Pport=abc**, thao tác **toInteger()** sẽ lỗi **khi Provider được tính**, không nhất thiết ở dòng định nghĩa map. Nên có thông báo validation rõ ràng khi dữ liệu có thể sai.

### 2.1. Không dùng map để tạo Provider lồng nhau

Giả sử cấu hình chứa **service** và tên property bổ sung **endpoint.orders**, **endpoint.billing**, ...:

~~~groovy
def service = providers.gradleProperty('service').orElse('orders')
~~~

Nếu viết:

~~~groovy
def nested = service.map { name ->
    providers.gradleProperty("endpoint.${name}")
}
~~~

Closure trả về **Provider<String>**. Về ý nghĩa, bạn nhận **Provider<Provider<String>>**, không phải Provider<String> mong muốn. **map** chỉ biến đổi giá trị; nó không tự động làm phẳng Provider do callback tạo ra.

Khi transformer trả về Provider, hãy chuyển sang **flatMap**.

## 3. flatMap: chọn hoặc nối một Provider khác

**Chữ ký về ý tưởng:**

~~~text
Provider<T>.flatMap(T -> Provider<R>) : Provider<R>
~~~

Ví dụ chọn endpoint theo service:

~~~groovy
def service = providers.gradleProperty('service').orElse('orders')

def endpoint = service.flatMap { name ->
    providers.gradleProperty("endpoint.${name}")
        .orElse("http://${name}.internal")
}
~~~

Cơ chế:

1. **service** chưa được lấy giá trị khi khai báo.
2. Khi **endpoint** được truy vấn, Gradle lấy giá trị từ **service**.
3. Nếu service là **orders**, callback tạo Provider cho property **endpoint.orders**.
4. **flatMap** lấy giá trị từ Provider được trả về, giúp endpoint cuối là **Provider<String>**, không có một Provider lồng bên trong.
5. Nếu **endpoint.orders** không được khai báo, **orElse** cung cấp **http://orders.internal**.
6. Với **-Pservice=billing -Pendpoint.billing=https://billing.example.invalid**, kết quả endpoint là chuỗi URL đã truyền.

Đoạn code là **ví dụ chọn chuỗi cấu hình**, không tự thực hiện HTTP request. Domain **.invalid** trong lệnh minh họa không phải endpoint đang hoạt động.

### 3.1. Khác nhau về loại kết quả của transformer

| Phép toán | Closure trả về | Kiểu Provider đầu ra | Dùng trong tình huống |
| --- | --- | --- | --- |
| **map** | Giá trị thường **R** | **Provider<R>** | Uppercase, parse số, tạo tên file |
| **flatMap** | **Provider<R>** | **Provider<R>** | Chọn Gradle property khác, lấy output Property của Task |
| **map** trả về Provider | **Provider<R>** | Provider lồng nhau về mặt ý nghĩa | Thường là sai mô hình |
| **flatMap** trả về chuỗi thường | **String** | Sai hợp đồng transformer | Chuyển sang **map** |

**Tư duy nhanh:** hỏi “closure này trả về chuỗi/file/số, hay một Provider?” Trả về dữ liệu thường thì dùng **map**; trả về Provider thì dùng **flatMap**.

### 3.2. flatMap và lựa chọn cấu hình theo môi trường

~~~groovy
def env = providers.gradleProperty('environment').orElse('local')

def apiUrl = env.flatMap { selected ->
    providers.gradleProperty("apiUrl.${selected}")
        .orElse("http://${selected}.example.invalid")
}
~~~

Khi chạy với **-Penvironment=staging -PapiUrl.staging=https://staging.example.invalid**, **apiUrl** phản ánh nguồn tương ứng. Không cần tạo if/else đọc các property khác nhau ngay ở configuration phase.

## 4. zip: kết hợp hai Provider độc lập

**Chữ ký về ý tưởng:**

~~~text
Provider<A>.zip(Provider<B>, (A, B) -> R) : Provider<R>
~~~

Ví dụ kết hợp service và environment:

~~~groovy
def service = providers.gradleProperty('service').orElse('orders')
def env = providers.gradleProperty('environment').orElse('local')

def target = service.zip(env) { name, environment ->
    "${name}@${environment}"
}
~~~

**target** là **Provider<String>**. Nếu dùng mặc định, nó mang giá trị **orders@local** khi được truy vấn. Callback có hai đối số là giá trị đã được lấy từ hai Provider; kết quả của callback ở đây là một String.

Cách gọi từ **ProviderFactory** cũng hợp lệ trong Gradle hiện đại:

~~~groovy
def target = providers.zip(service, env) { name, environment ->
    "${name}@${environment}"
}
~~~

Hai cách đều kết hợp Provider. Dạng thứ nhất tiện để nối method trên Provider nguồn; dạng thứ hai gọi trực tiếp **ProviderFactory.zip**. Không nhầm với **Groovy List.zip** hoặc các phương thức zip của thư viện khác.

### 4.1. Kết hợp nhiều hơn hai Provider

Với ba nguồn, có thể zip theo từng bước:

~~~groovy
def service = providers.gradleProperty('service').orElse('orders')
def env = providers.gradleProperty('environment').orElse('local')
def region = providers.gradleProperty('region').orElse('ap-southeast-1')

def serviceEnv = service.zip(env) { name, environment ->
    [name: name, environment: environment]  // Một Map thông thường
}

def summary = serviceEnv.zip(region) { left, rightRegion ->
    "${left.name}@${left.environment}/${rightRegion}"
}
~~~

**summary** là Provider<String>. Với các giá trị mặc định, kết quả là:

~~~text
orders@local/ap-southeast-1
~~~

Hoặc có thể sử dụng kết hợp **map** và **zip**:

~~~groovy
def upper = service.map { it.toUpperCase() }
def result = upper.zip(region) { name, code ->
    "${name}-${code}"
}
~~~

Dù có ba hay nhiều bước, **không gọi get() ở giữa**: giữ chuỗi Provider và chỉ yêu cầu giá trị ở nơi thật sự tiêu thụ.

### 4.2. Khi một nguồn chưa có giá trị

Với:

~~~groovy
def service = providers.gradleProperty('service')
def env = providers.gradleProperty('environment')
def target = service.zip(env) { name, environment ->
    "${name}@${environment}"
}
~~~

Nếu **service** hoặc **environment** chưa được cung cấp, **target** cũng **không có giá trị**. Hàm kết hợp không được gọi khi một nguồn thiếu.

Nếu cả hai đều không bắt buộc, thêm fallback trước khi zip:

~~~groovy
def safeService = providers.gradleProperty('service').orElse('orders')
def safeEnv = providers.gradleProperty('environment').orElse('local')

def safeTarget = safeService.zip(safeEnv) { a, b -> "${a}@${b}" }
~~~

Hoặc thêm fallback sau khi kết hợp:

~~~groovy
def targetOrFallback = target.orElse('unknown-target')
~~~

Hai cách có semantics khác nhau: **fallback trên từng nguồn** cho phép giữ những nguồn đã có; **fallback trên kết quả zip** thay toàn bộ kết quả nếu bất kỳ nguồn nào thiếu. Chọn theo yêu cầu thực tế.

## 5. Ví dụ build.gradle hoàn chỉnh, thực hành map + flatMap + zip

Tạo một thư mục thực hành có **Gradle Wrapper** hợp lệ, tạo hai tệp sau. Ví dụ dùng **Groovy DSL**.

**settings.gradle**:

~~~groovy
rootProject.name = 'provider-transform-demo'
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'base'
}

def service = providers.gradleProperty('service').orElse('orders')
def environment = providers.gradleProperty('environment').orElse('local')

def upperService = service.map { it.toUpperCase() }

def port = service.flatMap { name ->
    providers.gradleProperty("port.${name}").orElse('8080')
}

def target = service.zip(environment) { name, env ->
    "${name}@${env}"
}

tasks.register('showProviders') {
    group = 'help'
    description = 'Trình bày map, flatMap và zip'

    doLast {
        println "service=${service.get()}"
        println "environment=${environment.get()}"
        println "upper=${upperService.get()}"
        println "port=${port.get()}"
        println "target=${target.get()}"
    }
}
~~~

Mở terminal từ **root build**:

~~~bash
# Linux/macOS
./gradlew showProviders
~~~

~~~powershell
# Windows PowerShell
.\gradlew.bat showProviders
~~~

Với các giá trị mặc định, **năm dòng do task in ra**:

~~~text
service=orders
environment=local
upper=ORDERS
port=8080
target=orders@local
~~~

Log của Gradle còn có thông báo task và trạng thái build; đây chỉ là phần stdout từ **doLast**.

Thử truyền thuộc tính cụ thể:

~~~bash
./gradlew showProviders -Pservice=billing -Penvironment=staging -Pport.billing=9090
~~~

Với Windows, thay **./gradlew** thành **.\gradlew.bat**. Phần stdout của task:

~~~text
service=billing
environment=staging
upper=BILLING
port=9090
target=billing@staging
~~~

**Giải thích theo luồng dữ liệu:**

1. **providers.gradleProperty('service')** đọc nguồn Gradle property một cách lười; **orElse('orders')** cho Provider có mặc định.
2. **map** tạo upperService, biến chuỗi thành chữ hoa.
3. **flatMap** dùng service để tìm đúng property **port.billing** hoặc **port.orders**.
4. **zip** kết hợp service với environment thành nhãn target.
5. Những **get()** nằm trong **doLast**, tức ở task action, giúp ví dụ quan sát giá trị sau khi các Provider đã được nối.
6. Đối với build logic dùng lâu dài, nên khai báo input của task bằng **Property<T>** có annotation thích hợp và gán nguồn Provider vào nó, giúp Gradle quản lý incremental build và configuration cache chính xác hơn. Ví dụ **doLast** dùng closure là bài thực hành giải thích giá trị, chưa phải thiết kế plugin/typed task đầy đủ cho production.

**Không cần tính từng giá trị trước bằng get()**. Cốt lõi bài này là nối những Provider từ phần đầu của script và chỉ giải quyết khi task thật sự sử dụng.

## 6. Chuyển Provider thành đầu vào task

Trong Gradle, **Property<T>** là một dạng Provider có setter. Có thể thiết lập input bằng Provider:

~~~groovy
def mode = providers.gradleProperty('mode').orElse('debug')
def normalizedMode = mode.map { it.toUpperCase() }

def inputProperty = objects.property(String)
inputProperty.set(normalizedMode)
~~~

**inputProperty** vẫn là Property<String>, mang nguồn từ normalizedMode; **set(...)** không yêu cầu bạn gọi **normalizedMode.get()** ngay.

Với custom task, mô hình điển hình:

~~~groovy
abstract class PrintLabel extends DefaultTask {
    @Input
    abstract Property<String> getLabel()

    @TaskAction
    void printLabel() {
        println label.get()
    }
}

def rawLabel = providers.gradleProperty('label').orElse('hello')
def normalized = rawLabel.map { it.toUpperCase() }

tasks.register('printLabel', PrintLabel) {
    label.set(normalized)
}
~~~

Đoạn này là nội dung có thể đặt trong **build.gradle** Groovy DSL. Gradle có default script imports cho các type cơ bản như **DefaultTask**, **Property**, **Input** và **TaskAction**; nếu viết plugin Java/Groovy độc lập, cần khai báo imports theo cấu trúc source tương ứng.

Khi chạy:

~~~bash
./gradlew printLabel
~~~

Dòng do task in ra:

~~~text
HELLO
~~~

Lợi ích:

- **@Input** mô tả giá trị đầu vào của task để Gradle có thể theo dõi.
- **label.set(normalized)** nối Provider với Property; không cần ép lấy giá trị sớm.
- **@TaskAction** đọc **label.get()** khi task được thực thi.
- Nếu **-Plabel=world**, action in **WORLD**.

Lưu ý: custom task nên được định nghĩa trong **buildSrc/convention plugin** khi sử dụng nhiều nơi; class trong script thuận tiện để học, nhưng cấu trúc build logic lớn cần tổ chức và kiểm thử phù hợp.

## 7. flatMap với TaskProvider: nối producer và consumer đúng cách

Một ứng dụng đặc biệt quan trọng của **flatMap** là kết nối **đầu ra của task A** với **đầu vào task B**.

Giả sử có một task tạo file và một task đọc file đó. Mỗi task khai báo property có annotation để Gradle biết **đâu là output và đâu là input**.

Ví dụ độc lập cho **build.gradle** Groovy DSL:

~~~groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction

abstract class WriteMessage extends DefaultTask {
    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void writeMessage() {
        def destination = outputFile.get().asFile
        destination.parentFile.mkdirs()
        destination.setText('Hello from producer!\n', 'UTF-8')
    }
}

abstract class ReadMessage extends DefaultTask {
    @InputFile
    abstract RegularFileProperty getInputFile()

    @TaskAction
    void readMessage() {
        println inputFile.get().asFile.getText('UTF-8').trim()
    }
}

def producer = tasks.register('writeMessage', WriteMessage) {
    outputFile.set(layout.buildDirectory.file('generated/message.txt'))
}

tasks.register('readMessage', ReadMessage) {
    inputFile.set(producer.flatMap { task ->
        task.outputFile
    })
}
~~~

**Giải thích:**

1. **tasks.register('writeMessage', WriteMessage)** trả về **TaskProvider<WriteMessage>**.
2. **producer.flatMap { task -> task.outputFile }** lấy **RegularFileProperty**, chính là một Provider cho file được sản xuất.
3. **inputFile.set(...)** kết nối Provider này vào **@InputFile** của ReadMessage.
4. Gradle có thể nhận diện producer từ liên kết output → input, tự sắp thứ tự thực hiện khi chọn **readMessage**, không phải tự đoán đường dẫn hoặc ép thêm **dependsOn** chỉ vì file trùng tên.
5. **@TaskAction** của producer gọi **outputFile.get()** ở execution phase; file được tạo khi task chạy.
6. Consumer đọc file của producer qua input property đã nối.

Với Wrapper và Gradle/JDK tương thích, chạy:

~~~bash
./gradlew readMessage
~~~

Phần stdout của action reader:

~~~text
Hello from producer!
~~~

Gradle có thể in **> Task :writeMessage** và **> Task :readMessage**, trạng thái build, cùng những log khác. Lần chạy kế tiếp có thể có trạng thái UP-TO-DATE tùy inputs/outputs và điều kiện môi trường.

**Quan trọng:** chính việc **nối Property đầu ra được annotate trực tiếp** vào Property đầu vào cho Gradle biết task dependency. Không nên nghĩ rằng hai task tự có quan hệ chỉ vì cùng nhắc tới một đường dẫn file.

### 7.1. Sai lầm phá mất dependency

Đoạn dưới là **ví dụ sai**, không chạy như lời khuyên:

~~~groovy
// SAI: tạo một Provider riêng, không giữ metadata producer đúng cách.
def file = providers.provider {
    layout.buildDirectory.file('generated/message.txt').get().asFile
}
~~~

Một Provider được tạo độc lập bằng **providers.provider { ... }** không tự bảo đảm mang dependency của task đã sản xuất file; nó có thể làm consumer tìm file trước khi producer chạy.

Cũng tránh:

~~~groovy
// SAI về ý tưởng: ép lấy file lúc cấu hình/biến đổi sai cách.
def rawFile = producer.get().outputFile.get().asFile
~~~

Dòng này ép hiện thực hóa task và lấy giá trị quá sớm, làm mất lợi ích của lazy task configuration. Hướng đúng là **producer.flatMap { it.outputFile }** và truyền nó sang input property.

**Lưu ý kỹ:** với **TaskProvider.flatMap**, transformer cần trả về **Provider/Property đầu ra** đã được Gradle annotate phù hợp; **map** dùng khi cần biến một giá trị có sẵn thành giá trị thường. Không đọc output file trong configuration phase nếu producer chưa chạy. Các ví dụ task output/input nâng cao cần tuân thủ Gradle configuration-cache requirements.

## 8. Kết hợp flatMap và map trên output

Khi cần lấy tên file từ output property, có thể nối:

~~~groovy
def producedFile = producer.flatMap { task ->
    task.outputFile
}

def fileName = producedFile.map { regularFile ->
    regularFile.asFile.name
}
~~~

- **flatMap** lấy **Provider<RegularFile>** từ task producer và mang thông tin phụ thuộc của output phù hợp.
- **map** biến **RegularFile** thành **String** (tên file), nên dùng **map** thay cho flatMap ở bước này.
- **fileName** vẫn là một Provider<String>.

Nếu lấy nội dung file:

~~~groovy
def text = producedFile.map { regularFile ->
    regularFile.asFile.getText('UTF-8')
}
~~~

**Đừng đọc text lúc cấu hình**. Nhưng với việc kết nối input có nội dung file phục vụ task khác, hãy khai báo input kiểu phù hợp và bảo đảm Gradle đã biết producer. Việc file tồn tại hay chưa là điều kiện thực tế khi Provider được truy vấn; không phải chỉ vì có map mà Gradle tự chạy producer trong mọi ngữ cảnh. Đây là lý do nên truyền Provider qua **task input** thay vì gọi **text.get()** trong configuration phase.

## 9. Giá trị vắng mặt: absent, null, getOrElse và orElse

Provider có thể không có giá trị, chẳng hạn **providers.gradleProperty('optionalFlag')** khi không truyền property đó.

| API | Tác dụng | Có giữ Provider không? |
| --- | --- | --- |
| **get()** | Lấy giá trị; thất bại nếu absent | Không, trả giá trị T |
| **getOrNull()** | Lấy T hoặc null nếu absent | Không |
| **getOrElse(default)** | Lấy T nếu có, ngược lại trả default T | Không |
| **isPresent()** | Hỏi có giá trị hay không | Không, trả boolean |
| **orElse(default)** | Tạo Provider với fallback T | Có |
| **orElse(otherProvider)** | Tạo Provider dùng nguồn fallback khi nguồn chính absent | Có |

Ví dụ:

~~~groovy
def primary = providers.gradleProperty('buildLabel')
def withFallback = primary.orElse('local')

tasks.register('showLabel') {
    doLast {
        println withFallback.get()
    }
}
~~~

Nếu không có **buildLabel**, task in **local**. **primary.get()** sẽ lỗi nếu bạn dùng trong trường hợp này, còn **primary.getOrElse('local')** lấy ngay một String thay vì trả Provider; khác rõ với **orElse**.

### 9.1. map/flatMap/zip khi nguồn absent

- **map:** nếu nguồn absent, Provider dẫn xuất cũng absent; closure không được gọi.
- **flatMap:** nếu nguồn absent, Provider kết quả cũng absent. Nếu callback tạo Provider absent, kết quả cũng absent.
- **zip:** nếu **bất kỳ** nguồn nào absent, Provider kết quả absent; combiner không được gọi.
- **map/flatMap/zip:** callback có thể trả **null** theo API tương ứng; kết quả được xem là **không có giá trị**. Không dùng null như một giá trị thay thế ổn định trong workflow này.

**Absent không giống chuỗi rỗng.** Với property được khai báo là **-Pservice=**, Provider có thể có giá trị **""** (String rỗng). **orElse('orders')** không tự thay chuỗi rỗng bằng **orders** vì nguồn *có* giá trị. Nếu muốn thay cả giá trị rỗng, dùng map hoặc logic lọc có chủ đích rồi kết hợp fallback phù hợp.

Ví dụ chuẩn hóa nội dung rỗng:

~~~groovy
def service = providers.gradleProperty('service')
    .map { value -> value.trim() }
    .map { value -> value.isEmpty() ? 'orders' : value }
    .orElse('orders')
~~~

Chuỗi này giữ Provider lazy và xử lý cả **absent** (orElse) lẫn **blank** (map). Tránh lẫn lộn giữa logic “giá trị không tồn tại” và “giá trị tồn tại nhưng không hợp lệ”.

### 9.2. Gọi isPresent có thể làm phát sinh đánh giá

**isPresent()** là API hỏi trạng thái Provider và có thể khiến Gradle đánh giá nguồn/chuỗi cần thiết để xác định có giá trị. Không nên gọi nó hàng loạt ở configuration phase chỉ để “debug lazy” rồi ngạc nhiên vì cấu hình trở nên eager.

Tương tự, việc in trực tiếp object Provider không cho bạn nội dung String giống **get()**. Nếu muốn xem kết quả trong một bài tập, hãy in ở task action, và cần biết Provider có giá trị hoặc có fallback.

## 10. Provider biến đổi không nên có tác dụng phụ

Một transformer **map/flatMap/zip** có thể được Gradle gọi khi cần giá trị, và có thể được gọi nhiều lần tùy cách dùng, cấu hình cache và nguồn dữ liệu. Vì thế, tránh:

~~~groovy
// KHÔNG NÊN: tác dụng phụ trong transformer.
def label = providers.gradleProperty('service').map { name ->
    new File('label.txt').text = name
    name.toUpperCase()
}
~~~

Lỗi tư duy: **map** là để **mô tả biến đổi giá trị**, không phải để viết file. Tác vụ tạo file nên là **Task** với **@OutputFile** và **@TaskAction**, input được Gradle quản lý.

Tương tự, tránh đọc biến môi trường bằng **System.getenv(...)** hoặc đọc file tùy ý bên trong transformer nếu Gradle đã có API Provider phù hợp:

~~~groovy
// Nên dùng nguồn Provider do Gradle quản lý:
def branch = providers.environmentVariable('BUILD_BRANCH')
def normalized = branch.map { it.trim() }
~~~

Điều này giúp Gradle quan sát input của cấu hình và giảm nguy cơ configuration cache không nhận diện được trạng thái bên ngoài. Nếu cần dùng một kết quả process hoặc file, xem **providers.exec**, **providers.fileContents**, **ValueSource** hay API task input/output tương ứng; không tự thêm I/O vô điều kiện vào closure biến đổi.

### 10.1. Configuration cache và captured state

Gradle có thể lưu chuỗi Provider theo giá trị hoặc theo phép tính. Nếu closure transformer giữ tham chiếu tới object không tương thích configuration cache (ví dụ Project/Task ở chỗ execution không được phép), build có thể thất bại khi dùng **--configuration-cache**.

Tránh transformer chụp toàn bộ **project**, **Gradle** hoặc mutable object ngoài phạm vi mà không cần. Nên lấy dữ liệu qua Provider được Gradle cung cấp, tổ chức custom task thành typed properties, và làm các phép biến đổi càng thuần, càng rõ càng tốt.

Ví dụ thay vì:

~~~groovy
// Không nên tùy tiện lấy project.version trong transformer task input.
def label = providers.gradleProperty('prefix').map { p ->
    "${p}-${project.version}"
}
~~~

Có thể đưa version thành Provider đầu vào thích hợp và **zip** với prefix, khi nguồn và thời điểm lấy giá trị đã được xác định rõ. Cần hiểu rằng những giá trị cấp Project chỉ có ý nghĩa trong configuration phase; lựa chọn cách nối/chuyển chúng sang Provider phụ thuộc mô hình build đang viết.

## 11. Kotlin DSL: cùng ý tưởng, cú pháp khác

Những phép toán là API Gradle chung. Ví dụ tương ứng trong **build.gradle.kts**:

~~~kotlin
val service = providers.gradleProperty("service").orElse("orders")
val environment = providers.gradleProperty("environment").orElse("local")

val uppercase = service.map { it.uppercase() }

val port = service.flatMap { name ->
    providers.gradleProperty("port.$name").orElse("8080")
}

val target = service.zip(environment) { name, env ->
    "$name@$env"
}

tasks.register("showProviders") {
    doLast {
        println("service=${service.get()}")
        println("upper=${uppercase.get()}")
        println("port=${port.get()}")
        println("target=${target.get()}")
    }
}
~~~

Groovy DSL dùng closure **{ name -> ... }** và có thể bỏ ngoặc lời gọi; Kotlin DSL dùng lambda, type-safe accessors và cú pháp Kotlin. Không trộn cú pháp hai DSL trong cùng file. Với custom task trong Kotlin, nên dùng **abstract val input: Property<String>** có annotation phù hợp hoặc Kotlin typed plugin code để Gradle quản lý input.

## 12. Bài tập tự kiểm tra

### Bài 1: chọn map hay flatMap?

Có hai phép biến đổi:

~~~groovy
def a = providers.gradleProperty('port').map { it.toInteger() }
def b = providers.gradleProperty('service').flatMap { name ->
    providers.gradleProperty("port.${name}")
}
~~~

**Đáp án:** **a** dùng map vì closure trả về Integer; **b** dùng flatMap vì closure trả về Provider<String>. Nếu muốn giá trị port của **b** là Integer, nối thêm **.map { it.toInteger() }**.

### Bài 2: dự đoán zip absent

~~~groovy
def left = providers.gradleProperty('left')
def right = providers.gradleProperty('right')
def together = left.zip(right) { a, b -> "${a}:${b}" }
~~~

Chỉ có **-Pleft=one**, không truyền right. **Đáp án:** together **absent**; **together.get()** sẽ lỗi. Muốn có kết quả mặc định, dùng **right.orElse('two')** trước zip, hoặc fallback sau zip với semantics bạn chọn.

### Bài 3: điền đầu ra

~~~groovy
def code = providers.gradleProperty('code').orElse('core')
def upper = code.map { it.toUpperCase() }
def key = code.zip(upper) { a, b -> "${a}-${b}" }
~~~

Khi không truyền code, **key** khi đọc là **core-CORE**.

### Bài 4: vì sao không gọi get trong configuration?

~~~groovy
// Cách làm chưa tốt:
def name = providers.gradleProperty('name').get()
def upper = name.toUpperCase()
~~~

**Đáp án:** **get()** yêu cầu giá trị ngay lúc cấu hình, lỗi nếu property thiếu và làm mất lợi ích nối Provider. Nên dùng:

~~~groovy
def upper = providers.gradleProperty('name')
    .orElse('sample')
    .map { it.toUpperCase() }
~~~

### Bài 5: nối TaskProvider

Producer là **TaskProvider<WriteMessage>** có **@OutputFile RegularFileProperty outputFile**. Muốn đưa file này vào **@InputFile RegularFileProperty inputFile** của consumer, chọn câu nào?

~~~groovy
// (A)
inputFile.set(producer.flatMap { it.outputFile })

// (B) KHÔNG NÊN
inputFile.set(producersFilePath)
~~~

**Đáp án:** **(A)** vì Provider từ output property giúp Gradle giữ thông tin task dependency. Với **(B)** nếu chỉ đặt đường dẫn như một giá trị độc lập, Gradle không tự biết task nào cần tạo file ấy.

### Bài 6: fallback đặt ở đâu?

Giả sử cần hai nguồn **service** và **env**; nếu env thiếu, vẫn muốn giữ service hiện có và mặc định env là **local**. Hãy đặt **env.orElse('local')** trước khi zip. Nếu đặt **zip(...).orElse('unknown')** sau cùng, bạn sẽ mất phần service dù nó đang hiện hữu.

## 13. Checklist và lỗi thường gặp

| Hiện tượng | Nguyên nhân | Giải pháp |
| --- | --- | --- |
| Provider thành Provider lồng nhau | Dùng **map** nhưng closure trả Provider | Chuyển sang **flatMap** |
| **flatMap** báo sai kiểu | Closure trả chuỗi/số thay vì Provider | Dùng **map** cho dữ liệu thường |
| **get()** lỗi vì không có giá trị | Nguồn absent | Thêm fallback có chủ đích bằng **orElse**, hoặc kiểm tra/khai báo input bắt buộc |
| **zip** không gọi combiner | Một trong hai Provider absent | Xem nguồn, chọn fallback trước/sau zip |
| Chuỗi rỗng không kích hoạt orElse | Giá trị rỗng vẫn là giá trị hiện hữu | Chuẩn hóa blank trước bằng map |
| Task consumer chạy trước producer | Chỉ truyền path/file tĩnh, mất quan hệ output input | Dùng **producer.flatMap { it.outputFile }** với annotation đúng |
| Lấy output file quá sớm | Gọi **producer.get()** và **outputFile.get()** trong configuration | Giữ TaskProvider/Property, kết nối bằng flatMap |
| Build không ổn định vì map ghi file/chạy process | Transformer có tác dụng phụ, có thể bị gọi nhiều lần | Chuyển logic I/O vào task action hoặc API Gradle quản lý |
| Configuration cache báo capture object | Closure giữ Project/Task hoặc mutable state không hợp lệ | Sử dụng Provider rõ ràng, typed tasks, transformer thuần |
| In **println(provider)** thấy thông tin object | Chưa lấy giá trị hoặc đang in mô tả Provider | In trong task action bằng **get()**, sau khi có fallback hoặc xác nhận nguồn |
| Tưởng Provider được tính duy nhất một lần | Provider có thể là live, thay đổi khi truy vấn | Không dựa vào side effects hay số lần gọi transformer |

## Tài liệu Gradle chính thức

- [Properties and Providers](https://docs.gradle.org/current/userguide/properties_providers.html): **map**, **flatMap**, **zip**, **orElse**, cách nối Provider và Property.
- [Provider API](https://docs.gradle.org/current/javadoc/org/gradle/api/provider/Provider.html): chữ ký, absent values, query methods, transformer semantics.
- [ProviderFactory API](https://docs.gradle.org/current/javadoc/org/gradle/api/provider/ProviderFactory.html): nguồn Gradle/environment property và **ProviderFactory.zip**.
- [Best Practices for Tasks](https://docs.gradle.org/current/userguide/best_practices_tasks.html): nối producer/consumer với **flatMap** và rủi ro gọi get sớm.
- [Lazy Configuration](https://docs.gradle.org/current/userguide/lazy_configuration.html): mô hình task/property/provider lười.
- [Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): tạo task qua **register**, tránh hiện thực hóa không cần thiết.

**Điểm cần nhớ:** **map** biến đổi giá trị, **flatMap** nối hoặc chọn Provider khác, **zip** kết hợp hai Provider. Thực hành tốt nhất là giữ chuỗi lazy, gắn nó vào **Property/Input** của task, và chỉ lấy giá trị khi task thực thi hoặc Gradle cần giải quyết nó.