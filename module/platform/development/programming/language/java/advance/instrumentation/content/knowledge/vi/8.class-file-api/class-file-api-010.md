# Chọn bộ phân giải phù hợp class loader để tránh nạp lớp ngoài ý muốn

## 1. Vấn đề trong Java Class-File API

Khi sử dụng **Java Class-File API** để tạo, biến đổi hoặc kiểm tra bytecode, có những thời điểm công cụ cần biết quan hệ kế thừa và interface của các lớp xuất hiện trong bytecode. Ví dụ, khi tính `StackMapTable` tại điểm hợp nhất hai nhánh điều khiển, công cụ có thể phải xác định kiểu chung phù hợp của hai giá trị tham chiếu.

Java Class-File API cung cấp interface **`java.lang.classfile.ClassHierarchyResolver`** cho việc tra cứu thông tin phân cấp lớp. Bẫy quan trọng khi viết **Java agent** là: bộ phân giải mặc định sử dụng **reflection và system class loader**, có thể khiến những lớp chưa được nạp bị nạp thêm trong lúc chính JVM đang xử lý class loading.

Một transformer có thể gặp các hậu quả:

- Vô tình kích hoạt `ClassLoader.loadClass(...)`, làm thay đổi thời điểm và thứ tự nạp lớp.
- Tải sai class nếu lớp mục tiêu chỉ tồn tại trong một plugin loader, container loader, module layer hoặc một loader đặc biệt.
- Thấy thông tin hierarchy của **cùng tên binary name nhưng khác định nghĩa class**; tạo ra stack map frames không hợp lệ.
- Gặp recursion hoặc circularity khi đang transform một class rồi lại yêu cầu loader tải class liên quan.
- Phát sinh side effects từ custom loader: truy cập mạng, giải mã class, logging, đồng bộ hóa hoặc chính callback của agent.
- Gặp `NoClassDefFoundError`, `LinkageError`, `VerifyError` hoặc lỗi Class-File API vì không tìm được đúng hierarchy.

**Nguyên tắc trọng tâm:** **Muốn biết cấu trúc kế thừa không nhất thiết phải định nghĩa/nạp một lớp vào JVM.** Hãy chọn resolver lấy metadata trực tiếp từ class file/resource hoặc dữ liệu đã biết, trên **đúng không gian class loader**, thay vì mặc nhiên dùng reflection.

**Phiên bản:** `java.lang.classfile` và `ClassHierarchyResolver` là API chính thức từ **JDK 24** (JEP 484; các lần preview ở các JDK trước có API có thể khác). Các ví dụ dùng **JDK 24 trở lên**, không thể biên dịch với JDK 17. Phần khái niệm JVM và `java.lang.instrument` vẫn hữu ích cho Java 17+, nhưng **không sử dụng API `java.lang.classfile` trên Java 17**.

## 2. Vì sao Class-File API cần quan hệ kế thừa?

Trong bytecode có các **verification types** ở operand stack và local variables. Ở điểm hai nhánh cùng chuyển tới một instruction, verifier cần một trạng thái type có thể dùng chung.

Ví dụ logic:

```java
Object select(boolean flag) {
    Object result;
    if (flag) {
        result = new java.util.ArrayList<>();
    } else {
        result = new java.util.LinkedList<>();
    }
    return result;
}
```

Khi sinh hoặc tính lại stack map frames, công cụ có thể cần biết `ArrayList` và `LinkedList` kế thừa những lớp/interface nào để xác định loại giá trị phù hợp tại điểm hợp nhất. Việc chọn sai hierarchy có thể làm `StackMapTable` không nhất quán với bytecode thực tế.

Điều cần phân biệt:

- **Parse class file**: phần lớn thông tin có thể đọc từ bytes mà không cần nạp class; model được Class-File API xây dựng theo cơ chế lazy.
- **Sinh stack maps / verify class**: có thể cần thông tin của **các class khác** ngoài class đang được transform.
- **Load class bằng JVM**: tạo/liên kết một đối tượng `Class<?>` thông qua class loading; đây là hành vi khác với đọc tệp `.class`.
- **Initialize class**: thực hiện `<clinit>` khi các điều kiện khởi tạo được đáp ứng; class loading và initialization không đồng nghĩa. Dù reflection-based resolver không nhất thiết khởi tạo class, **việc nạp lớp sớm đã đủ là rủi ro** với agent.

Đối với các công việc tính frames, chính sách chọn resolver cần được quyết định **trước khi** sinh class file, không chờ `VerifyError` rồi sửa theo phỏng đoán.

## 3. `ClassHierarchyResolver` là gì?

Interface `java.lang.classfile.ClassHierarchyResolver` cung cấp thông tin hierarchy cho Class-File API khi tạo stack maps và kiểm tra bytecode. Thành phần cốt lõi:

```java
ClassHierarchyResolver.ClassHierarchyInfo getClassInfo(ClassDesc classDesc);
```

`ClassDesc` thuộc `java.lang.constant`, là **mô tả kiểu ở dạng ký hiệu**, không phải đối tượng `Class<?>`. Ví dụ `ClassDesc.of("com.example.Service")` chỉ xây dựng descriptor; nó **không tự load class Service**.

Theo đặc tả:

- Resolver trả `ClassHierarchyInfo` nếu biết class/interface tương ứng.
- Trả `null` nếu không biết; đây là tín hiệu để một resolver khác trong chuỗi `orElse(...)` thử tra cứu.
- Có thể ném `IllegalArgumentException` khi không thể cung cấp thông tin hợp lệ, ví dụ trường hợp class không được phép tra cứu.
- **Ứng dụng thông thường không cần gọi `getClassInfo` trực tiếp.** Class-File API gọi phương thức này trong quá trình tính stack maps/verification; ứng dụng nên cấu hình resolver bằng `ClassFile.ClassHierarchyResolverOption.of(...)`.

Cách gắn resolver:

```java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassHierarchyResolver;

ClassHierarchyResolver resolver = /* chọn theo môi trường lớp */;
ClassFile cf = ClassFile.of(
        ClassFile.ClassHierarchyResolverOption.of(resolver));
```

Đoạn trên **minh họa vị trí gắn cấu hình**, chưa phải chương trình độc lập; biến `resolver` cần được tạo từ một lựa chọn thực tế ở phần tiếp theo.

`ClassFile.of()` **không truyền option** sẽ dùng resolver mặc định. Với agent, đừng xem mặc định là đủ an toàn.

## 4. Phân biệt các loại resolver

### 4.1. `defaultResolver()`: đơn giản nhưng có nguy cơ nạp lớp

```java
ClassHierarchyResolver resolver =
        ClassHierarchyResolver.defaultResolver();
```

Theo Javadoc JDK 24, resolver mặc định lấy hierarchy bằng reflection qua **system class loader**. Nó **có thể nạp các lớp hệ thống chưa được nạp**, và **không thể tra cứu đúng** các lớp chỉ tồn tại trong class loader khác.

Sử dụng hợp lý trong môi trường kiểm thử/công cụ nhỏ khi việc nạp class được chủ động chấp nhận, tất cả lớp liên quan đều hiện diện chính xác qua system loader. **Không chọn mặc định cho bytecode transformer chạy trong lúc JVM nạp lớp** nếu có yêu cầu tránh nạp thêm hoặc hệ thống có nhiều loader.

### 4.2. `ofClassLoading(ClassLoader loader)`: reflection theo loader chỉ định

```java
ClassHierarchyResolver resolver =
        ClassHierarchyResolver.ofClassLoading(targetLoader);
```

Cách này dùng reflection với loader được cung cấp để đọc hierarchy. Nó giúp tránh lỗi **dùng nhầm system loader** khi lớp thuộc custom loader, nhưng **không** loại bỏ việc loader có thể được gọi để nạp thêm class.

Dùng khi bạn **có chủ đích cho phép class loading**, loader đã được chọn đúng, và thời điểm thực thi không nằm trên một đường biến đổi nhạy cảm. Đặc biệt cẩn thận với plugin/container loaders vì `loadClass` có thể gọi lại code ứng dụng hoặc có side effects.

**Đừng nhầm:** `Class.forName(name, false, loader)` (không yêu cầu initialization) **vẫn có thể load/link class**. Tham số `false` không biến reflection thành metadata-only resolution.

### 4.3. `ofClassLoading(MethodHandles.Lookup lookup)`: reflection có giới hạn quyền truy cập

```java
ClassHierarchyResolver resolver =
        ClassHierarchyResolver.ofClassLoading(lookup);
```

Sử dụng lớp mà một `MethodHandles.Lookup` cho phép truy cập; nếu class không truy cập được qua lookup, API có thể ném `IllegalArgumentException` thay vì trả `null`. Đây là một cơ chế kiểm soát visibility/lookup, **không phải cách bảo đảm không nạp class**.

Phù hợp khi việc load bằng reflection được cho phép và môi trường lookup cần được kiểm soát theo module/access rules.

### 4.4. `ofResourceParsing(ClassLoader loader)`: đọc resource `.class`, không dùng reflection để tạo `Class<?>`

```java
ClassHierarchyResolver resolver =
        ClassHierarchyResolver.ofResourceParsing(targetLoader);
```

Resolver đọc thông tin cấu trúc từ những **class file resources** mà loader đó tìm được, thay vì load class bằng reflection. Đây thường là lựa chọn tốt cho agent khi loader có thể cung cấp resource đúng.

Những giới hạn cần hiểu:

- **Resource lookup không đồng nghĩa class definition.** Custom loader có thể định nghĩa lớp từ bytes đã giải mã, sinh động, memory cache hoặc nguồn không có tệp `.class` truy cập được.
- `getResourceAsStream` có thể có hành vi riêng, I/O hoặc callback do loader cài đặt. “Không tạo `Class<?>` bằng reflection” **không đồng nghĩa zero side effects**.
- Nếu resource trong loader là **phiên bản khác** bytes đang được JVM định nghĩa, kết quả hierarchy có thể sai.
- Cần xem cơ chế delegation, module resources và việc cùng một tên lớp xuất hiện ở nhiều loader.

Đối với agent sử dụng `ClassFile` để sinh stack maps cho lớp vừa nhận ở `ClassFileTransformer.transform(...)`, `ofResourceParsing` thường an toàn hơn `ofClassLoading` **nếu** nguồn resource thực sự khớp với class definitions.

### 4.5. `ofResourceParsing(Function<ClassDesc, InputStream>)`: kiểm soát tuyệt đối nguồn bytes

Khi loader không cung cấp đúng resource, hãy dùng mapper có chủ đích:

```java
ClassHierarchyResolver resolver =
        ClassHierarchyResolver.ofResourceParsing(desc -> {
            // Chọn InputStream đúng theo ClassDesc, loader/module,
            // phiên bản artifact và bytes đã biết.
            // Trả null nếu không tìm thấy nguồn đáng tin cậy.
            return findClassFileStream(desc);
        });
```

Đây là **đoạn minh họa**, không phải mã độc lập: `findClassFileStream` đại diện cho hàm của hệ thống.

Mapper có thể đọc class file từ JAR, thư mục build, archive trong memory hoặc snapshot do agent quản lý. **Trả `null` khi không tìm được** để một resolver tiếp theo có thể thử; **không lén gọi `Class.forName`** để bù thiếu resource nếu mục tiêu là tránh nạp lớp. Stream cần được cung cấp đúng nội dung class file và quản lý đóng/mở theo API.

Nếu I/O stream gây `IOException`, resolver có thể chuyển thành `UncheckedIOException` trong quá trình tra cứu. Cần phân biệt **không tìm thấy** với **lỗi đọc** để không âm thầm tạo frame sai.

### 4.6. `of(interfaces, classToSuperClass)`: hierarchy hoàn toàn từ metadata

```java
import java.lang.constant.ClassDesc;
import java.util.List;
import java.util.Map;

ClassDesc task = ClassDesc.of("demo.Task");
ClassDesc base = ClassDesc.of("demo.Base");
ClassDesc impl = ClassDesc.of("demo.Impl");

ClassHierarchyResolver metadata =
        ClassHierarchyResolver.of(
                List.of(task),
                Map.of(impl, base,
                       base, ClassDesc.of("java.lang.Object")));
```

Đây là ví dụ cấu hình **metadata có giới hạn**: tập `interfaces` cho biết các kiểu được coi là interface; map cung cấp quan hệ class → superclass mà hệ thống biết. Ví dụ **chưa mô tả đầy đủ** mọi interface mà một class implement; để sinh frames trên bytecode thực, resolver phải trả hierarchy đủ chính xác cho các kiểu phát sinh, không chỉ hai entry mẫu.

Ưu điểm: không phải gọi loader hay đọc class file khi có đầy đủ metadata. Phù hợp với pipeline build/offline hoặc agent có snapshot hierarchy đáng tin cậy. Không phù hợp nếu hierarchy thiếu các lớp/interface cần thiết.

### 4.7. `orElse(...)`: phân tầng nguồn đáng tin

```java
ClassHierarchyResolver resolver =
        primaryResolver.orElse(fallbackResolver);
```

Nếu `primaryResolver` trả `null` vì không biết một kiểu, resolver thứ hai được hỏi. **Không** xem `orElse` là cơ chế bắt mọi exception hoặc sửa hierarchy sai của nguồn thứ nhất: khi nguồn thứ nhất trả một kết quả **sai nhưng khác null**, fallback không được hỏi.

Thứ tự được khuyến nghị cho công cụ instrumentation có archive/snapshot:

```text
1. Snapshot/metadata của đúng target loader & class bytes
        |
        +-- không biết kiểu -> 2. Resource parsing của đúng nguồn
                                    |
                                    +-- không biết kiểu
                                           -> 3. Resource của JDK/platform tin cậy
        |
        +-- vẫn không biết -> báo lỗi rõ ràng, không tự load bừa
```

Không dùng `orElse(defaultResolver())` như fallback vô điều kiện cho agent có yêu cầu **không load class**: nó vô tình tái đưa reflection vào pipeline.

### 4.8. `cached()`: giảm I/O nhưng có rủi ro stale data

```java
ClassHierarchyResolver resolver =
        underlyingResolver.cached();
```

Javadoc JDK 24 nêu rõ `cached()` mặc định **không thread-safe**, và cache lưu cả kết quả **`null`** khi một tên class chưa được biết đến. Điều này dẫn đến:

- Class mới xuất hiện sau lúc cache đã ghi nhận `null` có thể vẫn bị coi là không tồn tại.
- Class được redefine hoặc cập nhật resource thì cache cũ có thể phản ánh hierarchy không còn đúng.
- Cache theo tên nhưng dùng chung giữa **hai class loader** khác nhau sẽ trộn namespace và rất nguy hiểm.
- Cache lưu lâu có thể giữ những đối tượng hoặc thông tin không cần thiết; quy hoạch vòng đời theo loader/artifact/version.

Nếu có nhiều thread, dùng overload `cached(Supplier<Map<...>>)` với chiến lược map thread-safe phù hợp và thử nghiệm tính đúng đắn. Không dùng cache chung cho những loader có thể định nghĩa cùng binary name với hierarchy khác nhau.

## 5. Bảng chọn resolver theo tình huống

| Bối cảnh | Ưu tiên | Vì sao |
| --- | --- | --- |
| Agent đang transform class lúc load, có nguồn `.class` đáng tin từ loader | `ofResourceParsing(targetLoader)` | Đọc metadata class file, tránh yêu cầu JVM tạo `Class<?>` bằng reflection |
| Agent nhận class bytes từ memory/custom loader, resource có thể khác | `ofResourceParsing(Function)` với mapping đúng bytes + metadata riêng | Không lệ thuộc resource lookup sai phiên bản |
| Pipeline offline/build, đã có đủ hierarchy | `of(interfaces, classToSuperClass)` | Không load class, không I/O khi metadata đầy đủ |
| Sinh frames cho class riêng và JDK classes | Resolver nguồn riêng `orElse` resolver resource JDK phù hợp | Giữ thứ tự ưu tiên và không load class |
| Công cụ kiểm thử chỉ dùng system classpath và chấp nhận class loading | `defaultResolver()` | Dễ dùng, nhưng không phù hợp với agent tránh loading |
| Runtime có custom loader, class loading là chủ đích | `ofClassLoading(targetLoader)` | Reflection đúng loader, chấp nhận tác dụng phụ loading |
| Cần giới hạn theo quyền của `MethodHandles.Lookup` | `ofClassLoading(lookup)` | Kiểm soát access, **không** loại bỏ loading |
| Nhiều lần phân giải cùng artifact/loader bất biến | `cached()` hoặc cache có map phù hợp | Giảm chi phí, nhưng phải có policy invalidate/thread safety |

**Quy tắc:** Chọn resolver theo **nguồn chân lý của hierarchy** và **đúng class-loader namespace**, không theo cách viết ngắn nhất.

## 6. Ví dụ Java 24 chạy được: tính lại stack maps mà không gọi `loadClass` của nguồn class

Ví dụ tạo một class file thật bằng `javac`, sau đó đọc/biến đổi lại bằng Class-File API và một `ClassLoader` được cố ý thiết kế **chỉ cấp resource**. Mọi lời gọi `loadClass(...)` tới loader nguồn đều bị đếm và từ chối, nhờ đó chứng minh đoạn resolver không dùng class loading qua loader nguồn.

Lưu ý phạm vi phép thử: Java runtime tự nạp các **lớp JDK cần để chạy công cụ**, nhưng phép đo chỉ giám sát **loader dùng để cung cấp class file ứng dụng**. Không tuyên bố toàn JVM không có class nào được nạp.

Tạo thư mục:

```text
resolver-demo/
├── sample/
│   └── Example.java
└── NoLoadResolverDemo.java
```

### 6.1. `sample/Example.java`

```java
package sample;

import java.util.ArrayList;
import java.util.LinkedList;

public final class Example {
    public static Object choose(boolean first) {
        Object result;
        if (first) {
            result = new ArrayList<String>();
        } else {
            result = new LinkedList<String>();
        }
        return result;
    }
}
```

Phương thức có hai nhánh và một điểm hợp nhất kiểu reference. Class-File API sẽ được yêu cầu **sinh lại stack maps** khi build output.

### 6.2. `NoLoadResolverDemo.java`

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassHierarchyResolver;
import java.lang.classfile.ClassModel;
import java.lang.classfile.ClassTransform;
import java.lang.constant.ClassDesc;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public final class NoLoadResolverDemo {
    private NoLoadResolverDemo() {
    }

    // Cho phép đọc resources .class trong thư mục,
    // nhưng không cho phép dùng loader này để định nghĩa class.
    private static final class ResourceOnlyLoader extends ClassLoader {
        private final Path root;
        private int loadRequests;

        ResourceOnlyLoader(Path root) {
            super(null); // Không thiết lập parent loader Java.
            this.root = root.toAbsolutePath().normalize();
        }

        @Override
        public InputStream getResourceAsStream(String name) {
            Path file = root.resolve(name).normalize();

            // Không cho resource name thoát khỏi thư mục root.
            if (!file.startsWith(root)) {
                return null;
            }

            try {
                return Files.newInputStream(file);
            } catch (NoSuchFileException missing) {
                return null;
            } catch (IOException failure) {
                throw new UncheckedIOException(failure);
            }
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            loadRequests++;
            throw new ClassNotFoundException(
                    "Class loading is disabled: " + name);
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Path.of("classes");
        ResourceOnlyLoader files = new ResourceOnlyLoader(root);

        ClassHierarchyResolver appResources =
                ClassHierarchyResolver.ofResourceParsing(files);

        // Chỉ đọc class-file resources của JDK qua platform loader.
        // Không dùng defaultResolver() / ofClassLoading(...).
        ClassHierarchyResolver jdkResources =
                ClassHierarchyResolver.ofResourceParsing(
                        ClassLoader.getPlatformClassLoader());

        ClassHierarchyResolver resolver =
                appResources.orElse(jdkResources).cached();

        ClassFile cf = ClassFile.of(
                ClassFile.ClassHierarchyResolverOption.of(resolver),
                ClassFile.StackMapsOption.GENERATE_STACK_MAPS);

        byte[] source = Files.readAllBytes(
                root.resolve("sample/Example.class"));

        ClassModel model = cf.parse(source);
        byte[] rewritten = cf.transformClass(
                model, ClassTransform.ACCEPT_ALL);

        System.out.println("parsed=" +
                model.thisClass().asSymbol()
                        .equals(ClassDesc.of("sample.Example")));
        System.out.println("rebuilt=" + (rewritten.length > 0));
        System.out.println("verified=" + cf.verify(rewritten).isEmpty());
        System.out.println("sourceLoadRequests=" + files.loadRequests);
    }
}
```

Giải thích thiết kế:

1. `ResourceOnlyLoader` chỉ cung cấp `.class` bằng `getResourceAsStream(...)`. Nếu Class-File API hoặc cấu hình vô tình yêu cầu `loadClass` của loader này, chương trình báo sai/chặn lời gọi.
2. `appResources` tra cứu class của `sample` từ thư mục biên dịch. Nó không dựa trên system classpath để đoán hierarchy của lớp riêng.
3. `jdkResources` đọc resource class file JDK qua platform loader; nó không tương đương `defaultResolver()` dùng reflection. Trong ứng dụng đặc thù, có thể cần mapper tường minh từ module/JDK image để bảo đảm nguồn resources chính xác.
4. `orElse` ưu tiên hierarchy từ thư mục ứng dụng, sau đó mới dùng JDK resources.
5. `GENERATE_STACK_MAPS` yêu cầu Class-File API tính lại stack maps khi xây dựng output; không chỉ sao chép frame sẵn có. Tính đúng đắn phụ thuộc hierarchy đã chọn.
6. `ClassTransform.ACCEPT_ALL` chuyển tiếp class elements mà không chủ động đổi logic; ví dụ chỉ tập trung vào **chọn resolver và round-trip class file**.
7. `cf.verify(rewritten)` kiểm tra kết quả bằng API trong cùng context; đây là một lớp kiểm tra bổ sung, không thay thế thử nạp/chạy bằng JVM mục tiêu.
8. Chương trình **không dùng `Class.forName("sample.Example")`**; chỉ làm việc với bytes và `ClassModel`.

### 6.3. Biên dịch và chạy

Mở terminal ở thư mục `resolver-demo/`. Cần **JDK 24+** cho `java.lang.classfile`:

```bash
mkdir classes
javac --release 24 -d classes sample/Example.java NoLoadResolverDemo.java
java -cp classes NoLoadResolverDemo
```

Trên JDK 24 có class resources chuẩn và hỗ trợ Class-File API, stdout mong đợi:

```text
parsed=true
rebuilt=true
verified=true
sourceLoadRequests=0
```

Không có lời gọi `loadClass` đến `ResourceOnlyLoader`. Lệnh `javac` biên dịch cả hai class trước lúc chạy; chương trình runtime chỉ **đọc** `sample/Example.class`, không định nghĩa `sample.Example` thành một `Class<?>`.

**Lưu ý quan trọng về kiểm chứng:** `sourceLoadRequests=0` chỉ chứng minh resolver không gọi `loadClass` trên **loader nguồn đã instrument**. Nó không chứng minh `ClassFile` không mở resource, không có I/O, hoặc JVM không nạp bất kỳ class JDK nào phục vụ chính công cụ. Nếu muốn khẳng định chính xác mọi lần class loading trong môi trường có agent, cần thêm kiểm tra bằng `Instrumentation.getAllLoadedClasses()` hoặc theo dõi sự kiện class loading ở mức JVM.

Nếu JVM/hệ thống có chính sách module resource khác làm `jdkResources` không cung cấp một class file cần thiết, hãy thay fallback bằng **nguồn `jrt:/` hoặc archive có kiểm soát** thay vì quay lại reflection. Đó là vấn đề **không đủ nguồn hierarchy**, không phải lý do để tự động load tất cả lớp.

### 6.4. Đối chứng: vì sao đổi resolver có thể nguy hiểm?

Thay dòng lựa chọn resolver bằng:

```java
ClassHierarchyResolver resolver =
        ClassHierarchyResolver.ofClassLoading(files);
```

Lúc Class-File API cần hierarchy ngoài các thông tin đã có, nó có thể gọi `files.loadClass(...)` để cố lấy `Class<?>`. Loader demo sẽ từ chối và quá trình generation/verification có thể thất bại. **Đây là đoạn đối chứng về rủi ro**, không phải biến thể được khuyến nghị để chạy thành công.

Tương tự, dùng `ClassHierarchyResolver.defaultResolver()` có thể nạp bằng **system loader** và thấy một phiên bản `sample.Example` khác với file mà demo đang rewrite. Đối với agent phục vụ plugin/custom loaders, đó là vấn đề **tính đúng đắn** ngoài tác dụng phụ hiệu năng.

## 7. Chọn resolver trong `ClassFileTransformer` thật

Transformer nhận các tham số như:

```java
byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
```

Trong bài toán của agent, `loader` là **defining class loader** của class đang transform:

- `loader == null` biểu diễn bootstrap loader.
- `loader != null` là một đối tượng class loader cụ thể; không chắc đó là system loader.
- `className` thường là JVM internal name dùng dấu `/`.
- `classfileBuffer` là **bytes của lớp hiện đang được JVM xử lý**, có thể khác tệp `.class` mà một loader trả về qua resource lookup.
- Khi retransform, class bytes có thể được JVM cung cấp lại theo cơ chế khác với “đọc chính xác cùng tệp trên disk”.

Các lựa chọn:

### 7.1. Ưu tiên snapshot/bytes từ callback làm nguồn cho class hiện tại

Nếu resolver có thể cần hierarchy của chính class đang được transform, lựa chọn chính xác nhất thường là **`classfileBuffer` hiện tại** (hoặc metadata được rút ra từ cùng bytes), không mặc định đi đọc `loader.getResourceAsStream(className + ".class")` vì resource đó có thể:

- Không tồn tại (loader định nghĩa từ dữ liệu trong memory);
- Trỏ tới một version khác khi transformer đã xử lý trước đó;
- Được sinh/giải mã bằng một cách khác so với `loadClass`;
- Nằm trong module/JAR lồng nhau mà resource search thông thường không thấy.

Mapper `ofResourceParsing(Function)` cho phép trả `ByteArrayInputStream` từ snapshot bytes chính xác của class đích, rồi tìm những class phụ thuộc trong các nguồn riêng có **cùng class-loader namespace**.

**Đoạn code minh họa cho bước chọn stream** (không phải một chương trình độc lập):

```java
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.lang.classfile.ClassHierarchyResolver;
import java.lang.constant.ClassDesc;

ClassDesc target = ClassDesc.of("com.example.Service");
byte[] targetBytes = classfileBuffer.clone();

ClassHierarchyResolver resolver =
        ClassHierarchyResolver.ofResourceParsing(desc -> {
            if (desc.equals(target)) {
                return new ByteArrayInputStream(targetBytes);
            }

            // Phần còn lại phải đọc đúng nguồn của từng class
            // trong namespace và module của loader đích.
            return trustedStreamFor(desc);
        });
```

Đoạn này giả sử `classfileBuffer`/`trustedStreamFor` được cung cấp bởi transformer và hạ tầng của agent. **`trustedStreamFor` không phải hàm JDK**. Trong code thực, `target` được xác định từ tên lớp nội bộ ở callback, không hard-code tất cả lớp thành `com.example.Service`.

Nếu transformer chạy trong lúc JVM còn đang định nghĩa class, hãy tránh gọi `Class.forName` hoặc thực thi ứng dụng từ trong mapper. Nó có thể kích hoạt loader thêm lần nữa hoặc recursion.

### 7.2. Loader bootstrap cần nhánh riêng

Khi `loader == null`, **không gọi `loader.getResourceAsStream(...)`**. Có thể lấy hierarchy nền tảng từ nguồn JDK/module image và hierarchy các lớp agent bổ sung bootstrap search từ JAR đã biết. Không được mặc nhiên cho rằng platform loader nhìn thấy mọi class trong JAR được agent append vào bootstrap.

Với các class lõi `java.base`, có thể cân nhắc đọc class files qua resource/JRT phù hợp runtime. Với lớp ứng dụng nằm trên bootstrap search do agent thêm, cần lấy đúng archive/snapshot được append. Sự tồn tại của bootstrap loader không đồng nghĩa class bắt đầu bằng `java/`.

### 7.3. Không tái sử dụng resolver giữa hai loader không tương đương

Hai loader có thể định nghĩa **cùng binary name** với superclass khác nhau:

```text
Plugin loader A: com.demo.Task extends com.demo.BaseA
Plugin loader B: com.demo.Task extends com.demo.BaseB
```

`ClassDesc.of("com.demo.Task")` ở cả hai trường hợp tạo cùng mô tả ký hiệu, nhưng quan hệ hierarchy của hai định nghĩa **không giống nhau**. Một cache resolver dùng chung theo `ClassDesc` mà không phân biệt loader có thể làm stack maps sai.

Quy tắc: tạo resolver/cached context theo đúng **loader + module layer/artifact/version** khi các yếu tố đó có thể ảnh hưởng đến sự định nghĩa class. Không giữ mạnh một `ClassLoader` của plugin vô hạn chỉ để cache metadata.

## 8. Resource parsing vẫn cần thiết kế phòng ngừa

### Không được đánh đồng resource với class thực sự đã define

`ClassLoader.getResourceAsStream("com/demo/Foo.class")` là **resource lookup**. Nó không bắt buộc lấy đúng bytes mà `ClassLoader.loadClass("com.demo.Foo")` đã dùng. Một loader có thể dùng child-first delegation cho classes nhưng parent-first cho resources, hoặc mã hóa/biến đổi bytes trong `findClass`.

Khi nghi ngờ, ưu tiên **snapshot ở điểm define/transform** và metadata do build/deployment cung cấp. Nếu không đủ dữ liệu để tạo frames đáng tin, báo lỗi rõ ràng; không ghi class file mà bạn không thể chứng minh hợp lệ.

### Không xem “không load class” là “không có side effects”

Resolver đọc resources có thể chạy custom code của `getResourceAsStream`, mở file, đọc network storage, giải nén JAR hoặc thay đổi cache. Khi instrumentation hoạt động ở hot path, cần tránh I/O chậm, code reentrant và khóa có thể deadlock với loader.

Nên xây một **resource snapshot bất biến** hoặc cache có phạm vi hợp lý, đo latency và giới hạn số lần tra cứu.

### Cẩn thận với module và quyền truy cập

Java 9+ phân biệt class loader, module layer và access. Một class thuộc named module có thể không có resource nhìn thấy bằng cùng cách như class trên classpath thông thường. `MethodHandles.Lookup` cũng có giới hạn access riêng. Hãy xác nhận nguồn resource và nghĩa của hierarchy theo môi trường modules thực tế.

**Không sửa lỗi bằng cách luôn mở module hoặc bypass access** chỉ để parser đọc được classfile. Một stream được lấy từ nguồn đã tin cậy có thể đủ để tính metadata mà không thay đổi cơ chế module/runtime của ứng dụng.

## 9. Tính đúng đắn của cache và fallback

**Cache miss:** `cached()` có thể lưu **`null`**. Nếu một plugin tải class file mới sau khi cache đã nhận “không biết”, resolver cũ có thể không tự thấy bản mới. Cần tạo resolver mới hoặc quản lý invalidation theo version.

**Thread safety:** `cached()` mặc định **không thread-safe**. Agent đa luồng có thể đăng ký nhiều transformer và nạp lớp song song; chọn một resolver cache có chính sách đồng bộ phù hợp nếu chia sẻ giữa threads. Tùy biến `cached(Supplier<Map<...>>)` nếu cần map có đặc điểm thread-safety cụ thể.

**Fallback sai thứ tự:** Một resolver đọc system classpath trả kết quả thành công cho một tên lớp mà plugin cũng định nghĩa sẽ chặn việc hỏi nguồn plugin. Vì vậy phải **ưu tiên nguồn của class đích trước**; `orElse` không tự phát hiện kết quả sai.

**Fallback loading bất ngờ:** Nếu dùng `resourceResolver.orElse(ClassHierarchyResolver.defaultResolver())`, phần cuối vẫn có thể load class. Khi yêu cầu **không load**, mọi nhánh fallback cũng phải đáp ứng yêu cầu đó.

**Lỗi cần hiển thị:** Nếu hierarchy không đủ, không nên gắn tạm `java.lang.Object` cho mọi kiểu rồi giả định đúng. Stack map verification có ràng buộc về class/interface, arrays và assignment compatibility; “xấp xỉ” sai có thể dẫn tới `VerifyError` hoặc lỗi classfile generation.

## 10. Phân biệt các trạng thái lỗi

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Agent nạp thêm lớp khi rewrite bytecode | `defaultResolver()` hoặc `ofClassLoading(...)` dùng reflection | Chuyển sang resource/metadata resolver được kiểm soát và kiểm thử số class load |
| `ClassNotFoundException` trong custom loader | Reflection yêu cầu loader tìm class chưa nạp | Kiểm tra đường gọi, tránh dùng loading resolver trên hot path |
| `IllegalArgumentException` khi generate/verify | Thiếu hierarchy, class không truy cập được qua `Lookup`, hoặc bytecode không tương thích | Đối chiếu class/module/loader, bổ sung nguồn metadata đúng; đừng fallback loading mù |
| `UncheckedIOException` lúc phân giải resource | Stream `.class` có lỗi đọc | Sửa resource storage/source, log tên class/source, phân biệt với “không tìm thấy” |
| `VerifyError` sau khi transform | Stack frames không phù hợp class thực tế | Kiểm tra hierarchy đúng **defining loader**, class version, control flow và bytecode |
| Plugin A chạy đúng, plugin B lỗi với cùng tên class | Cache/lookup lấy nhầm namespace hoặc resource parent-first | Tách resolver theo loader/module/artifact, test duplicate binary names |
| Gọi `getResourceAsStream` nhưng không tìm class | Loader chỉ hỗ trợ memory definitions, remote/JAR nested/module resource | Sử dụng `ofResourceParsing(Function)` và nguồn bytes/snapshot trực tiếp |
| `loader == null` gây `NullPointerException` | Agent gọi method trên bootstrap loader không tồn tại dưới dạng object | Xử lý bootstrap như case riêng, dùng JDK resource/source có kiểm soát |
| Transformer gây stack overflow / circularity | Resolver kích hoạt class loading quay lại callback | Loại bỏ reflection trong callback, tránh phụ thuộc recursive và reentrant I/O |
| Cache không thấy class mới cập nhật | `cached()` giữ cả giá trị không biết, stale metadata | Tạo resolver/cache theo epoch/version và reset khi thay đổi |
| Thay `StackMapsOption` để “né lỗi” | Drop frames không đúng có thể làm class fail verifier | Cung cấp resolver chính xác và generate/verify frame đúng yêu cầu |

## 11. Checklist triển khai Class-File API trong Java agent

1. **Xác định JDK:** `java.lang.classfile` dùng chính thức từ JDK 24; nếu agent phải chạy Java 17, chọn công cụ bytecode tương thích khác, ví dụ ASM/Byte Buddy.
2. **Xác định nguồn hierarchy:** biết class bytes được định nghĩa bởi loader nào, module nào, trong phiên bản artifact nào.
3. **Tránh nạp class ngoài ý muốn:** không dùng `defaultResolver()` hoặc `ofClassLoading(...)` trong transformer nhạy cảm nếu không chấp nhận việc loading.
4. **Chọn resource/metadata resolution:** ưu tiên `ofResourceParsing(...)` hoặc `of(...)`; dùng callback bytes khi resource ngoài không đáng tin.
5. **Gắn resolver vào context:** `ClassFile.of(ClassFile.ClassHierarchyResolverOption.of(resolver), ...)`; đừng trông chờ context mặc định sẽ biết custom loaders.
6. **Tính stack maps có kiểm soát:** `GENERATE_STACK_MAPS` khi thực sự cần, hiểu `STACK_MAPS_WHEN_REQUIRED` có thể reuse những frames tương thích, và không xóa frames bừa.
7. **Fallback không được phá chính sách:** mọi `orElse(...)` phải có nguồn hierarchy đúng và không trigger class loading khi đó là ràng buộc.
8. **Cache theo namespace:** tránh trộn class cùng tên từ loader khác nhau; quản lý stale negative cache và thread safety.
9. **Kiểm tra output:** verify class file và thử nạp chạy trên JVM mục tiêu, quan sát `VerifyError`, `ClassFormatError`, `LinkageError`.
10. **Đo rủi ro runtime:** số lần tra cứu resource, latency callback, class load ngoài ý muốn, recursion và tác động tới startup.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `ClassHierarchyResolver.defaultResolver()` không phù hợp với agent đang chạy trong `ClassFileTransformer`?

**Đáp án:** Resolver mặc định dùng reflection/system loader, có thể **nạp class chưa được nạp** và tra cứu sai nếu class chỉ tồn tại trong custom loader. Khi đang transform, hành vi đó có thể làm sai loading order hoặc gây recursion.

**Câu 2.** Dùng `ofResourceParsing(targetLoader)` có bảo đảm nhận đúng bytes đang được JVM define không?

**Đáp án:** Không. Resource lookup có thể khác đường định nghĩa class, đặc biệt với memory definitions, custom loaders, modules và JAR lồng nhau. Cần kiểm tra nguồn hoặc dùng mapper với snapshot bytes đúng.

**Câu 3.** `ClassDesc.of("demo.Service")` có tự load lớp `demo.Service` không?

**Đáp án:** Không. `ClassDesc` là mô tả ký hiệu. Class loading xảy ra nếu một resolver hoặc code khác chọn gọi loader/reflection tương ứng.

**Câu 4.** `primary.orElse(fallback)` có tự bắt `IllegalArgumentException` của primary rồi chuyển fallback không?

**Đáp án:** Không. Fallback được hỏi khi primary trả **`null`** vì không biết class, không phải cơ chế bắt mọi exception.

**Câu 5.** Vì sao không thể dùng cache `ClassDesc → ClassHierarchyInfo` chung cho hai plugin loaders?

**Đáp án:** Hai loader có thể định nghĩa cùng tên class với superclass/interfaces khác nhau. Cache theo descriptor mà không ràng buộc namespace có thể lấy sai hierarchy và làm stack frames không hợp lệ.

**Câu 6.** Vì sao `cached()` cần xét vòng đời và đa luồng?

**Đáp án:** Mặc định cache không thread-safe và có lưu cả kết quả chưa biết (`null`); nếu hierarchy thay đổi hoặc nhiều thread tra cứu đồng thời, kết quả có thể stale hoặc gặp vấn đề concurrency.

## 13. Tài liệu chính thức

- [JEP 484 — Class-File API](https://openjdk.org/jeps/484): chuẩn hóa API trong Java 24.
- [Java SE 24 — `java.lang.classfile` package](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/package-summary.html): parse/transform/generate, tính stack maps và cấu hình resolver.
- [Java SE 24 — `ClassHierarchyResolver`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassHierarchyResolver.html): `defaultResolver`, `ofClassLoading`, `ofResourceParsing`, `of`, `orElse`, `cached`.
- [Java SE 24 — `ClassFile.ClassHierarchyResolverOption`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.ClassHierarchyResolverOption.html): tác động của resolver lên stack map generation/verification.
- [Java SE 24 — `ClassFile.StackMapsOption`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.StackMapsOption.html): `GENERATE_STACK_MAPS`, `STACK_MAPS_WHEN_REQUIRED` và `DROP_STACK_MAPS`.
- [Java SE 24 — `ClassFile` API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html): `ClassFile.of`, `parse`, `transformClass`, `verify`.
- [Java SE 24 — `ClassTransform`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassTransform.html): `ClassTransform.ACCEPT_ALL` và biến đổi class models.

**Ghi nhớ:** Trong Class-File API, **đọc hierarchy không cần đồng nghĩa với load class**. Với instrumentation, hãy chọn **resolver dựa trên resource/metadata của đúng class-loader namespace**, gắn nó qua `ClassFile.ClassHierarchyResolverOption`, tránh `defaultResolver`/`ofClassLoading` khi class loading là rủi ro, và kiểm thử cả stack maps lẫn class loading thực tế.
