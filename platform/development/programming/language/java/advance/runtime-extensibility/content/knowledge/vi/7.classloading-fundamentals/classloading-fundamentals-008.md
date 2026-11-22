# Khóa nạp lớp, loader hỗ trợ song song và nguy cơ bế tắc

Trong ứng dụng Java có cơ chế mở rộng lúc chạy (runtime extensibility), nhiều luồng có thể yêu cầu nạp các lớp từ cùng một plugin hoặc các plugin khác nhau. JVM phải bảo đảm một class loader không định nghĩa trùng một lớp, nhưng đồng bộ hóa quá rộng có thể khiến việc nạp các lớp độc lập bị nối đuôi nhau. Khi hai class loader phụ thuộc chéo, việc giữ khóa trong lúc gọi sang loader khác còn có thể gây **deadlock**: mỗi luồng giữ một khóa mà luồng kia đang chờ.

Bài học tập trung vào ba vấn đề có quan hệ trực tiếp:

1. **Khóa nạp lớp là gì?** ClassLoader khóa đoạn tìm lớp đã nạp, ủy quyền, tìm định nghĩa và liên kết khi cần để bảo vệ tính nhất quán.
2. **Loader hỗ trợ song song (parallel-capable) thay đổi điều gì?** Các yêu cầu nạp tên lớp khác nhau có thể dùng những khóa khác nhau, trong khi các yêu cầu cùng một tên vẫn được phối hợp an toàn.
3. **Deadlock hình thành và được xử lý ra sao?** Đặc biệt khi tùy biến class loader, dùng ủy quyền qua lại giữa plugin, hoặc trộn khóa loader với khóa ứng dụng.

Mục tiêu thực hành là hiểu đúng hợp đồng của **ClassLoader.loadClass**, **getClassLoadingLock** và **registerAsParallelCapable** trong Java 17+, biết thiết kế plugin loader an toàn hơn và chẩn đoán sự cố thay vì chỉ thêm synchronized.

## 1. Vì sao nạp lớp cần khóa?

Trong JVM, một lớp được nhận diện không chỉ bởi tên nhị phân như app.plugins.Parser mà còn bởi **class loader định nghĩa lớp đó**. Hai loader có thể định nghĩa hai lớp cùng tên và tạo ra hai đối tượng Class khác nhau. Tuy nhiên, một loader không được vô tình định nghĩa cùng một tên hai lần do hai luồng đua nhau.

Tưởng tượng hai thread cùng yêu cầu tải demo.plugin.Task qua một loader:

~~~text
Thread T1                  Loader L                    Thread T2
    |                         |                            |
    |--- loadClass(Task) ---->|<---- loadClass(Task) -------|
    |                         |                            |
    |                Kiểm tra findLoadedClass               |
    |                Tìm và định nghĩa lớp (nếu cần)        |
    |                Lưu Class đã tải, resolve khi yêu cầu   |
    |                         |                            |
    |<-------- cùng một Class hợp lệ, không define trùng ---|
~~~

Nếu cả T1 và T2 đều thấy lớp chưa nạp và cùng gọi defineClass cho cùng một tên trong cùng loader, sẽ dẫn đến cạnh tranh và có thể phát sinh LinkageError do định nghĩa trùng, ngoài các vấn đề bất nhất khác. Khóa giúp bao bọc thao tác **check–then–load/define** để chỉ một luồng thực hiện đường đi tạo lớp cần thiết cho tên đó.

Đồng bộ hóa còn liên quan đến việc ủy quyền cho loader cha hoặc tìm class của chính loader. ClassLoader không thể chỉ khóa mỗi lệnh defineClass mà bỏ qua việc kiểm tra trạng thái và phân nhánh trước đó; một custom loader phải giữ tính nhất quán của toàn bộ quy trình.

### Khóa ở đâu trong cài đặt mặc định?

Với cơ chế ủy quyền chuẩn của Java, đường đi của ClassLoader.loadClass(String, boolean) có dạng khái quát:

~~~java
// MÃ MINH HỌA CƠ CHẾ; KHÔNG PHẢI CẢI BIÊN NGUYÊN VĂN JDK
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {
    synchronized (getClassLoadingLock(name)) {
        Class<?> c = findLoadedClass(name);
        if (c == null) {
            try {
                c = getParent() != null
                        ? getParent().loadClass(name)
                        : findBootstrapClassOrNullIllustration(name);
            } catch (ClassNotFoundException ex) {
                c = findClass(name);
            }
        }
        if (resolve) {
            resolveClass(c);
        }
        return c;
    }
}
~~~

Đoạn trên **chỉ diễn giải ý tưởng**, không thể biên dịch trực tiếp vì findBootstrapClassOrNullIllustration là tên giả để biểu diễn bước tìm lớp bootstrap. Không chép đoạn này làm bản override sản xuất. Đường đi thực tế của ClassLoader bao gồm những chi tiết xử lý bootstrap và exception theo JDK; điều quan trọng là **synchronized(getClassLoadingLock(name))**, **findLoadedClass**, ủy quyền cho parent rồi mới **findClass** khi phù hợp.

Một custom loader thường chỉ cần **override findClass(String)** để tự tìm bytecode. Kế thừa loadClass mặc định giúp giữ quy tắc parent-first và khóa do JDK quản lý. Chỉ override loadClass khi thực sự cần một chính sách ủy quyền khác và đã kiểm tra kỹ tương tác đồng thời.

## 2. Khóa của loader thông thường và loader parallel-capable

Phương thức được bảo vệ **getClassLoadingLock(String className)** là nơi ClassLoader chọn đối tượng khóa phục vụ nạp tên lớp.

- **Loader chưa đăng ký parallel-capable:** mọi tên lớp cùng trả về **chính đối tượng loader** (this). Nghĩa là T1 nạp A sẽ chặn T2 nạp B qua loader đó, dù A và B độc lập.
- **Loader đã đăng ký parallel-capable:** loader duy trì một đối tượng khóa cho **từng tên lớp**. T1 nạp A và T2 nạp B có thể đồng thời tiến hành; nếu cả hai cùng nạp A thì vẫn dùng chung khóa của A.
- Các tên lớp khác nhau không có nghĩa là mọi công việc diễn ra song song: cả hai có thể chờ parent, đọc chung kho JAR, đụng khóa của cache, khóa ứng dụng hoặc phụ thuộc lẫn nhau.

Bảng sau phân biệt cơ chế:

| Điều kiện | Loader không parallel-capable | Loader parallel-capable |
| --- | --- | --- |
| Hai thread nạp **cùng tên A** trên cùng loader | Cùng khóa this | Cùng khóa dành cho A |
| Hai thread nạp **A và B** trên cùng loader | Vẫn cùng khóa this | Hai khóa theo tên khác nhau |
| Nạp A qua loader L1, B qua loader L2 | Mỗi loader có đối tượng khóa riêng | Khóa gắn với từng loader và tên |
| Vòng ủy quyền L1 → L2 → L1 | Có nguy cơ deadlock | **Vẫn có nguy cơ**, tùy tên/khóa và thứ tự |
| Tính an toàn của cache/URL/JAR tùy biến | Phải tự bảo đảm | **Vẫn phải tự bảo đảm** |
| Việc khởi tạo tĩnh của lớp | Theo cơ chế JVM riêng | Theo cơ chế JVM riêng |

Với loader thông thường, một synchronized method như loadClass được đồng bộ trên this cũng tạo ra mô hình khóa toàn loader. Với parallel-capable, hợp đồng quan trọng là **giữ khóa của getClassLoadingLock(name)**, chứ không vô tình thêm một khóa chung bao quanh cả thao tác.

### Tại sao không bỏ khóa hoàn toàn?

Parallel-capable **không** đồng nghĩa nhiều luồng được phép define cùng tên tùy ý. Khóa theo tên vẫn phối hợp findLoadedClass, ủy quyền và findClass. Nếu custom loadClass bỏ khóa hoặc tự gọi defineClass cạnh tranh, đăng ký parallel-capable không tự sửa được các lỗi race hay LinkageError.

Nói cách khác, parallel-capable là **thay đổi độ mịn của đồng bộ hóa**: từ một khóa cho cả loader thành nhiều khóa theo tên. Nó không miễn trừ trách nhiệm đồng bộ, không thay thế hợp đồng class loading và không tự quyết định cấu trúc phụ thuộc của plugin.

## 3. Đăng ký parallel-capable đúng cách

ClassLoader có phương thức protected static **registerAsParallelCapable()**. Một lớp loader tùy biến muốn hỗ trợ song song phải gọi phương thức này trong **static initializer của chính lớp loader**. Việc đăng ký cần xảy ra trước khi lớp được sử dụng để tạo các instance theo vòng đời bình thường.

~~~java
public final class PluginClassLoader extends ClassLoader {
    static {
        if (!registerAsParallelCapable()) {
            throw new ExceptionInInitializerError(
                    "Không đăng ký được parallel-capable class loader");
        }
    }

    public PluginClassLoader(ClassLoader parent) {
        super(parent);
    }

    // Override findClass khi có nguồn bytecode riêng.
    // Ở đây kế thừa loadClass mặc định để bảo toàn parent-first và khóa JDK.
}
~~~

**Đây là ví dụ cấu trúc loader**, có thể biên dịch nếu lưu đúng tên tệp PluginClassLoader.java; nó chưa thêm chức năng tìm bytecode mới. Cơ chế đăng ký được áp dụng cho **lớp ClassLoader cụ thể**, không phải một cờ bật toàn JVM cho mọi instance hay mọi subclass.

Điều kiện quan trọng là **toàn bộ chuỗi superclass có liên quan phải đã đăng ký parallel-capable**. Nếu một lớp loader cha do bạn viết không đăng ký, lớp con không thể đơn giản gọi registerAsParallelCapable() để vượt qua giới hạn đó. Trong một hệ thống plugin nhiều tầng loader, hãy kiểm tra lớp gốc trung gian thay vì chỉ nhìn lớp con cuối cùng.

### Các trường hợp cần tránh

~~~java
// MÃ MINH HỌA LỖI THIẾT KẾ, KHÔNG DÙNG TRONG SẢN PHẨM
public final class SlowPluginClassLoader extends ClassLoader {
    static {
        registerAsParallelCapable();
    }

    @Override
    protected synchronized Class<?> loadClass(String name, boolean resolve)
            throws ClassNotFoundException {
        return super.loadClass(name, resolve);
    }
}
~~~

Mặc dù lớp đã thử đăng ký, từ khóa **synchronized** gắn trên phương thức override khóa **toàn bộ this**. Hai yêu cầu nạp A và B sẽ vẫn phải vào phương thức lần lượt. Gọi super.loadClass bên trong không xóa được khóa ngoài. Lỗi phổ biến khác là **synchronized(this)** bao cả khối loadClass, hoặc dùng cùng một static/global lock cho mọi plugin.

Một cách khác cũng sai là thêm registerAsParallelCapable() nhưng viết custom loadClass bỏ qua synchronized(getClassLoadingLock(name)). Đăng ký không bảo đảm tự động rằng code tùy biến của bạn an toàn; class loader phải áp dụng đúng cơ chế khóa trong đường đi của mình.

**Ưu tiên thực tế:** nếu mục đích duy nhất là tải bytecode từ một nguồn khác, hãy override findClass và kế thừa loadClass. Chỉ thay cơ chế ủy quyền khi có yêu cầu về plugin isolation hoặc namespace rõ ràng.

## 4. Ví dụ Java 17 chạy được: kiểm tra khóa theo tên lớp

Ví dụ này chạy độc lập, không tải mã độc hoặc cố gây deadlock. Nó dùng **getClassLoadingLock** để quan sát trực tiếp sự khác biệt về **identity của đối tượng khóa** mà JDK trả về; vì chỉ so sánh tham chiếu nên không có nondeterminism từ lịch chạy thread.

Tạo tệp **ClassLoadingLockDemo.java**:

~~~java
public class ClassLoadingLockDemo {
    public static void main(String[] args) {
        inspect("Serial", new SerialLoader());
        inspect("Parallel", new ParallelLoader());
    }

    private static void inspect(String label, LockProbe probe) {
        Object a1 = probe.lock("demo.A");
        Object a2 = probe.lock("demo.A");
        Object b = probe.lock("demo.B");

        System.out.println(label
                + ": same-name=" + (a1 == a2)
                + ", different-names-share-lock=" + (a1 == b));
    }

    private interface LockProbe {
        Object lock(String name);
    }

    private static final class SerialLoader extends ClassLoader
            implements LockProbe {
        SerialLoader() {
            super(ClassLoadingLockDemo.class.getClassLoader());
        }

        @Override
        public Object lock(String name) {
            return getClassLoadingLock(name);
        }
    }

    private static final class ParallelLoader extends ClassLoader
            implements LockProbe {
        static {
            if (!registerAsParallelCapable()) {
                throw new ExceptionInInitializerError(
                        "Parallel registration failed");
            }
        }

        ParallelLoader() {
            super(ClassLoadingLockDemo.class.getClassLoader());
        }

        @Override
        public Object lock(String name) {
            return getClassLoadingLock(name);
        }
    }
}
~~~

Lưu với mã hóa UTF-8, mở terminal trong thư mục chứa tệp và chạy bằng **JDK 17 hoặc mới hơn**:

~~~bash
javac -encoding UTF-8 ClassLoadingLockDemo.java
java ClassLoadingLockDemo
~~~

Đầu ra xác định:

~~~text
Serial: same-name=true, different-names-share-lock=true
Parallel: same-name=true, different-names-share-lock=false
~~~

**Giải thích từng kết quả:**

1. Với SerialLoader (không đăng ký), getClassLoadingLock("demo.A") và getClassLoadingLock("demo.B") đều trả về this, nên cả so sánh cùng tên và khác tên đều true.
2. Với ParallelLoader, phương thức được đăng ký trong static initializer. Tên demo.A được ánh xạ ổn định tới một khóa; hai lần hỏi A trả cùng tham chiếu, còn demo.B nhận khóa khác.
3. Hai lớp này là hai lớp con trực tiếp của ClassLoader, nên SerialLoader **không** tự hưởng trạng thái parallel-capable của lớp cha; một subclass phải đăng ký chính nó. ClassLoader nền của JDK là một lớp đã hỗ trợ hợp đồng song song.
4. Ví dụ đo **identity của khóa**, không đo tốc độ. Nó không chứng minh rằng hệ thống I/O hay parent loader có thể thực sự nạp hai class nhanh gấp đôi. Những phần đó phải được benchmark hoặc kiểm thử đồng thời riêng.

Trong một lớp loader thực tế, những khóa được quan sát là thứ mà triển khai chuẩn loadClass dùng để đồng bộ khi xử lý yêu cầu.

## 5. Deadlock giữa hai class loader diễn ra như thế nào?

Một deadlock cổ điển có hai loader riêng **L_A** và **L_B**, đều sử dụng khóa toàn loader. Giả sử L_A cần hỏi L_B về lớp B, trong khi L_B cần hỏi L_A về lớp A. Hai thread hoạt động song song:

~~~text
Thread T1                                  Thread T2
---------                                  ---------
Giữ lock(L_A) khi load A                    Giữ lock(L_B) khi load B
    |                                            |
    |  Gọi L_B.loadClass(B)                      |  Gọi L_A.loadClass(A)
    v                                            v
Chờ lock(L_B)  <-------------------------->  Chờ lock(L_A)
    |                                            |
Không thể nhả lock(L_A)                   Không thể nhả lock(L_B)
                     DEADLOCK
~~~

Cả hai luồng đều chờ một khóa mà luồng còn lại đang giữ. Không luồng nào có thể hoàn thành lời gọi nạp lớp hiện tại để nhả khóa của mình. Đây là **vòng chờ tài nguyên** (*circular wait*); tăng số lượng thread, sửa timeout của yêu cầu HTTP hay thêm synchronized khác thường không giải quyết nguyên nhân.

Trong một hệ plugin, nguyên nhân có thể là:

- Plugin A dùng class loader A để nạp lớp và fallback sang loader của plugin B.
- Plugin B cũng fallback sang loader A để giải quyết dependency.
- Hai lệnh nạp chạy đồng thời, các loader giữ khóa trong khi ủy quyền.
- Hoặc code plugin tùy biến giữ một monitor riêng quanh quá trình load, rồi gọi sang loader khác tạo thành vòng chờ tương tự.

**Lưu ý phạm vi:** ví dụ trên là mô hình khóa toàn loader. Với parallel-capable, L_A và L_B có thể giữ các khóa theo **tên lớp** khác nhau; tình huống deadlock cụ thể này có thể giảm hoặc biến mất nếu hai luồng không yêu cầu trùng tên và không có khóa bổ sung. Tuy nhiên, một vòng chờ có thể vẫn xuất hiện nếu hai bên cần cùng những khóa theo tên, chờ tải phụ thuộc, giữ monitor của plugin hoặc chạy khởi tạo lớp. Không thể kết luận “đã đăng ký parallel-capable thì hết deadlock”.

### Vì sao cross-delegation dễ tạo vòng lặp?

Cơ chế ủy quyền mặc định thường đi từ loader con sang loader cha theo một quan hệ có hướng, không tạo chu kỳ. Khi thiết kế plugin loader tùy biến, người triển khai đôi khi bổ sung logic:

~~~text
Plugin A loader
   -> nếu không thấy class thì hỏi Plugin B loader
   -> Plugin B loader lại hỏi Plugin A loader
~~~

Ngay cả khi chỉ có một thread, vòng ủy quyền thiếu điều kiện dừng có thể dẫn đến đệ quy vô hạn/StackOverflowError hoặc lỗi nạp lớp tùy tình huống. Khi có nhiều thread và các loader giữ khóa khác nhau, nó có thể trở thành deadlock. Hai triệu chứng này có chung nguyên nhân kiến trúc: **đường phân giải lớp không có hướng phụ thuộc nhất quán**.

Giải pháp bền vững không phải thử mọi loader cho tới khi có kết quả; phải định nghĩa rõ mỗi namespace do loader nào sở hữu, nhóm API nào do parent quản lý và quan hệ phụ thuộc được phép của plugin.

## 6. Parallel-capable giúp gì, và điều gì vẫn có thể bị khóa?

Giả sử một loader L xử lý đồng thời yêu cầu nạp hai lớp độc lập demo.plugin.JsonCodec và demo.plugin.XmlCodec.

**Loader không parallel-capable:**

~~~text
T1: acquire lock(L) ---- load JsonCodec ---- release
T2:                      wait lock(L)        ---- load XmlCodec ----
~~~

**Loader parallel-capable:**

~~~text
T1: acquire lock(L, JsonCodec) ---- load JsonCodec ---- release
T2: acquire lock(L, XmlCodec)  ---- load XmlCodec  ---- release
~~~

Đây là sơ đồ **khả năng tiến hành đồng thời**, không phải cam kết tốc độ hay timeline chính xác của JVM. Khi cả hai tên lớp cùng cần loader cha, đọc chung JAR hoặc truy cập cache có khóa, vẫn có điểm chờ chung.

Đối với hai lời gọi **cùng tên**, dù loader parallel-capable, cả hai sẽ dùng cùng khóa cho tên đó. Điều này giữ an toàn cho findLoadedClass/defineClass. Một loader không thể hy sinh điều kiện “định nghĩa một lần” chỉ để tăng concurrency.

### Những khóa khác không biến mất

| Nguồn chờ | Vì sao parallel-capable không tự giải quyết? |
| --- | --- |
| Loader cha không parallel-capable | Loader cha vẫn khóa toàn instance khi phân giải các lớp qua nó |
| Cache hoặc kho bytecode riêng | Nếu cache dùng synchronized/global lock, các lời gọi vẫn tuần tự |
| Khóa trên đối tượng plugin hoặc registry | Những monitor ngoài getClassLoadingLock không đổi |
| Giao thức cross-delegation có chu kỳ | Một vòng phụ thuộc vẫn có thể gây chờ lẫn nhau |
| Khởi tạo tĩnh của class | JVM quản lý đồng bộ khởi tạo lớp theo một cơ chế khác |
| Tác vụ I/O hoặc mạng chậm | Có thể làm tăng thời gian giữ khóa, không phụ thuộc loại khóa |
| Tải cùng một tên class | Đúng mục đích vẫn phải phối hợp bằng cùng khóa |

Điều này đặc biệt quan trọng khi có loader theo tenant, theo plugin hoặc cơ chế reload. Không nên dùng một khóa global “để an toàn” bao tất cả plugin, bởi nó làm mất lợi ích đồng thời và dễ mở rộng vòng chờ giữa các plugin.

## 7. Phân biệt nạp lớp (loading), liên kết (linking) và khởi tạo (initialization)

Một tình huống treo trong quá trình tải plugin có thể đến từ **khóa class loader**, nhưng cũng có thể do **khởi tạo tĩnh của lớp**, cần xác định đúng.

- **Loading:** tìm bytecode và tạo ra đối tượng Class gắn với defining loader; ClassLoader.loadClass là điểm vào quen thuộc.
- **Linking:** xác minh, chuẩn bị và phân giải tham chiếu khi cần. resolveClass có thể yêu cầu liên kết một lớp đã nạp, không phải khởi tạo nó.
- **Initialization:** chạy các static field initializer và khối static initialization của lớp khi có tác nhân kích hoạt, ví dụ new, gọi phương thức static không hằng theo ngữ nghĩa JVM hoặc Class.forName(name, true, loader).

ClassLoader.loadClass("demo.Plugin") thông thường **không tự chạy static initializer của demo.Plugin**. Trong khi đó Class.forName("demo.Plugin", true, loader) yêu cầu khởi tạo lớp. Nếu class A và class B có quá trình khởi tạo tĩnh đan chéo, hai thread có thể chờ nhau ở khóa khởi tạo nội bộ JVM, ngay cả khi các loader đều parallel-capable.

~~~text
T1: đang khởi tạo class A -> trong <clinit> cần dùng class B
T2: đang khởi tạo class B -> trong <clinit> cần dùng class A
T1 chờ B khởi tạo; T2 chờ A khởi tạo -> có thể deadlock
~~~

Không nên nhìn thấy một stack trace chứa tên ClassLoader rồi mặc định lỗi nằm ở getClassLoadingLock. Hãy xem thread đang **BLOCKED chờ monitor loader**, đang chờ class initialization, hay đơn giản là đọc JAR/đợi I/O.

Một lỗi dễ gặp khác là làm công việc nặng hoặc kích hoạt plugin từ static initializer của lớp loader: vừa khó chẩn đoán vừa có thể tái nhập cơ chế nạp lớp đúng lúc các thành phần chưa sẵn sàng. Static initializer của custom loader nên chỉ thực hiện các thao tác đăng ký/cấu hình rất nhỏ và chắc chắn.

## 8. Cách triển khai class loader tùy biến an toàn hơn

### 8.1. Giữ đường đi mặc định nếu có thể

Nếu host chỉ cần tải bytecode từ thư mục plugin, JAR hay kho mã riêng, hãy ưu tiên **override findClass** hoặc dùng loader có sẵn phù hợp. Đừng viết lại toàn bộ loadClass chỉ để đọc thêm một nguồn class: đường đi mặc định đã xử lý cache, ủy quyền và đồng bộ hóa.

Ví dụ khung API minh họa (không phải chương trình độc lập, vì ClassBytesRepository là thành phần do ứng dụng phải cài đặt):

~~~java
final class RepositoryClassLoader extends ClassLoader {
    static {
        if (!registerAsParallelCapable()) {
            throw new ExceptionInInitializerError("Registration failed");
        }
    }

    private final ClassBytesRepository repository;

    RepositoryClassLoader(ClassLoader parent, ClassBytesRepository repository) {
        super(parent);
        this.repository = repository;
    }

    @Override
    protected Class<?> findClass(String name) throws ClassNotFoundException {
        byte[] bytes = repository.find(name);
        if (bytes == null) {
            throw new ClassNotFoundException(name);
        }
        return defineClass(name, bytes, 0, bytes.length);
    }
}
~~~

Mã khung chưa định nghĩa ClassBytesRepository, chưa kiểm tra code source/signing/package sealing và chưa bàn về độ tin cậy bytecode; nó **chỉ cho thấy điểm override**. Trong sản phẩm, repository phải có hành vi thread-safe khi findClass có thể chạy song song cho các tên khác nhau, kiểm tra bytecode và đóng gói đúng quy tắc của loader.

### 8.2. Nếu phải override loadClass, dùng khóa theo tên và quy tắc rõ ràng

Một loader child-first cho namespace riêng của plugin có thể cần override loadClass. Khi đó:

1. Dùng **synchronized(getClassLoadingLock(name))** quanh phần findLoadedClass/ủy quyền/findClass và resolve nếu cần.
2. Kiểm tra **findLoadedClass(name)** trước khi cố định nghĩa lớp.
3. Xác định rõ namespace nào **parent-first** (java.*, javax.*, jakarta.*, API host, giao diện SPI chung) và namespace nào thuộc plugin; không cố tự định nghĩa lớp java.*.
4. Có fallback có kiểm soát và ném **ClassNotFoundException** khi không tìm được, không thử tìm vòng tròn giữa mọi loader.
5. Chỉ gọi **resolveClass** theo hợp đồng, không tự ép mọi lớp khởi tạo tĩnh trong lúc giữ khóa.
6. Tránh giữ thêm một synchronized(this), static/global monitor hoặc khóa registry xuyên qua lời gọi sang loader khác.
7. Với nhiều plugin, thiết lập đồ thị phụ thuộc **không có chu kỳ** hoặc kiến trúc chia sẻ API qua loader cha; coi quan hệ phụ thuộc là đầu vào được kiểm tra lúc kích hoạt plugin.

Việc gọi getClassLoadingLock(name) bên trong một custom loader **không tự khiến nó parallel-capable**: nếu chưa đăng ký thành công, phương thức vẫn trả về this. Vì vậy phải kết hợp **đăng ký đúng lớp, chuỗi superclass hợp lệ và code tải lớp tuân thủ khóa**.

### 8.3. Không giữ khóa ứng dụng trong khi gọi loader tùy biến

Ví dụ nguy hiểm:

~~~java
// MÃ MINH HỌA RỦI RO: pluginRegistry là đối tượng do host quản lý.
synchronized (pluginRegistry) {
    // Loader có thể gọi ngược mã ứng dụng hoặc loader khác.
    pluginLoader.loadClass(pluginName);
}
~~~

Nếu luồng khác đang giữ khóa class loader mà cần truy cập pluginRegistry, cặp thao tác có thể hình thành vòng chờ. Hãy lấy cấu hình/snapshot cần thiết trước, nhả khóa registry, rồi mới gọi loader theo chính sách an toàn của hệ thống. Nếu cần ghi nhận kết quả, kiểm tra lại trạng thái/version khi quay vào registry.

Tương tự, không gọi callback plugin, dependency resolver có thể chạy code người dùng hoặc I/O không kiểm soát trong một critical section rộng. Thời gian giữ khóa lớn tăng xác suất gặp lỗi đồng thời và làm việc dừng plugin khó đoán.

## 9. Chẩn đoán deadlock và nghẽn nạp lớp

Một JVM có vẻ treo khi bật plugin có thể rơi vào một trong ba trạng thái:

1. **Deadlock thật:** vòng chờ khóa giữa hai hay nhiều thread, không thể tự tiến triển.
2. **Lock contention:** các thread chờ một loader đang xử lý class chậm, nhưng cuối cùng có thể hoàn thành.
3. **I/O wait hoặc class initialization wait:** stack nằm trong đường nạp/khởi tạo nhưng nguyên nhân không phải monitor class loader.

Cần chứng cứ thread dump ở **thời điểm sự cố**; không kết luận chỉ từ thời gian chờ hoặc từ việc CPU thấp.

### Bước 1 — lấy thread dump

Tìm PID của tiến trình, dùng lệnh phù hợp với JDK và quyền thực thi. Với JDK có công cụ diagnostic:

~~~bash
jcmd <pid> Thread.print -l
~~~

Hoặc:

~~~bash
jstack -l <pid>
~~~

Trong lệnh thực tế, **thay <pid> bằng số PID**, chẳng hạn 12345; hai dòng trên là mẫu lệnh không chạy nguyên văn. Trong môi trường container cần chạy ở namespace/process thích hợp và có quyền attach. Thu thập nhiều dump cách nhau một khoảng ngắn có ích để phân biệt tiến trình đang thay đổi với vòng chờ cố định.

### Bước 2 — đọc quan hệ giữ và chờ khóa

Quan sát các trường:

- Thread **BLOCKED (on object monitor)** hoặc thông tin waiting-to-lock/locked trên cùng monitor loader hay đối tượng khóa tên lớp.
- Stack frame liên quan tới ClassLoader.loadClass, getClassLoadingLock, findClass, defineClass, URLClassLoader, loader framework hoặc custom plugin loader.
- Dòng **waiting to lock** của T1 trỏ tới monitor mà T2 đang giữ, đồng thời T2 chờ monitor mà T1 đang giữ: đây là bằng chứng vòng chờ.
- Nếu là parallel-capable, monitor khóa theo tên có thể là một đối tượng **java.lang.Object**, không hiển thị ngay tên lớp; cần kết hợp stack và log của resolver để ánh xạ.
- Nếu là class initialization, chú ý frame khởi tạo tĩnh và trạng thái thread chờ lớp; không vội kết luận getClassLoadingLock là nguồn gốc.

Ví dụ minh họa từ góc nhìn điều tra (không phải stdout thật của một JDK cụ thể):

~~~text
T1: giữ monitor khóa L_A, chờ monitor khóa L_B
T2: giữ monitor khóa L_B, chờ monitor khóa L_A
=> circular wait: class-loader deadlock

T3: chờ monitor khóa L_C
T4: giữ monitor khóa L_C và đang đọc JAR chậm
=> contention/I-O: chưa đủ bằng chứng deadlock
~~~

JVM có thể phát hiện và in một số Java-level deadlock tự động. Tuy vậy, một số dạng chờ liên quan tới class initialization hoặc native/I/O có thể không xuất hiện trong danh sách deadlock tự động; vẫn cần phân tích stack và trạng thái thực tế.

### Bước 3 — bổ sung quan sát có kiểm soát

- Ghi **loader identity** (tên, loại, parent, plugin/tenant ID) và **binary class name** lúc bắt đầu/tìm/fallback/kết thúc, đặc biệt trước khi gọi loader khác.
- Log trạng thái đăng ký parallel-capable ở giai đoạn khởi tạo và xác nhận code override dùng getClassLoadingLock(name). Đừng suy luận từ tên lớp loader.
- Kiểm tra đường phân giải class có chu kỳ: A → B → A, fallback qua mọi loader, hay khóa registry nắm giữ lúc cross-delegation.
- Dùng các công cụ JVM/JFR phù hợp để đo lock contention, số lần/độ trễ class load, nhưng hiểu rõ giới hạn dữ liệu do từng JDK và cấu hình ghi sự kiện cung cấp.
- Đối chiếu thời điểm phát hành plugin, thay đổi classpath, hot reload và policy loader. Một bản nâng cấp có thể thêm dependency khiến hai plugin vốn độc lập trở nên phụ thuộc chéo.

Java có **ThreadMXBean.findDeadlockedThreads()** để hỗ trợ dò deadlock ở mức monitor và ownable synchronizer mà JVM hỗ trợ; nó không phải bằng chứng duy nhất và không nhận diện mọi kiểu chờ tài nguyên. Hãy xem thread dump thực tế trước khi chọn biện pháp sửa.

## 10. Thiết kế phòng tránh theo từng nguyên nhân

| Nguyên nhân | Cách sửa ưu tiên | Lưu ý |
| --- | --- | --- |
| Tất cả tên lớp bị tuần tự hóa trên một custom loader | Đăng ký parallel-capable đúng cách, dùng getClassLoadingLock(name) | Cần an toàn cho cache/nguồn bytecode dùng chung |
| Override synchronized loadClass giữ khóa this | Bỏ khóa bao ngoài và tuân thủ khóa theo tên | Không bỏ đồng bộ hóa check–load–define |
| Hai plugin loader gọi qua lại không có thứ tự | Thiết kế đồ thị phụ thuộc có hướng, loại chu kỳ | Parallel-capable không sửa được kiến trúc vòng |
| Loader con tự nạp bản sao service API của host | Dùng parent-first cho API chung | Tránh hai định danh Class cho cùng giao diện |
| Giữ khóa plugin registry khi gọi loadClass | Tách snapshot cấu hình khỏi thời gian nạp lớp | Kiểm tra phiên bản/trạng thái khi cập nhật lại |
| Static initializer kích hoạt dependency vòng | Giảm side effect, tách init thành lifecycle có kiểm soát | Đây có thể là initialization deadlock riêng |
| Đọc JAR/remote source dưới khóa lâu | Cache hoặc chuẩn bị dữ liệu có kiểm soát, tránh blocking không cần thiết | Giữ nguyên kiểm tra quyền/độ tin cậy và define-once |
| Lỗi khó tái hiện | Dựng test concurrent load + timeout, thu thread dump | Không coi test chạy một lần là bảo đảm không deadlock |

### Với hệ plugin cần hot reload

Một phiên plugin mới thường có class loader mới. Những thread/instance từ phiên cũ có thể giữ tham chiếu tới loader cũ, dẫn đến chờ hoặc leak nếu không dọn đúng vòng đời. Khi stop/reload, quản lý rõ:

- Trạng thái **ACTIVE → STOPPING → CLOSED**, từ chối công việc mới khi đang dừng.
- Kết thúc hoặc hủy công việc đang chạy theo chính sách; không giữ monitor của plugin manager rồi chờ thread khác join trong khi thread đó cần chính monitor ấy.
- Đóng URLClassLoader hoặc nguồn tài nguyên khi không còn sử dụng, giải phóng strong references để class có cơ hội unload.
- Không dùng một registry toàn cục có khóa lớn để đồng thời nạp, dừng và kích hoạt plugin; tách giai đoạn quyết định trạng thái khỏi các thao tác có thể chờ hoặc gọi ra ngoài.

Việc gọi **URLClassLoader.close()** giải phóng tài nguyên mà loader sở hữu theo hợp đồng nhưng không tự unload các class đã định nghĩa; unload còn phụ thuộc các tham chiếu tới class, instance và loader. Tương tự, registerAsParallelCapable() không phải cơ chế unload hay điều phối lifecycle.

## 11. Kiểm thử concurrency có ý nghĩa

Bài kiểm tra khóa theo tên trong phần 4 xác nhận cơ chế mà API cung cấp, nhưng hệ thống plugin thực cần kiểm thử đúng đường tải class của mình.

Các tình huống cần thử:

1. **Cùng một tên trên cùng một loader, nhiều thread:** mọi thread nhận cùng Class hoặc lỗi nạp hợp lệ theo cùng nguyên nhân; không có định nghĩa lặp hay race gây LinkageError.
2. **Hai tên độc lập trên cùng loader:** không bị tuần tự hóa do khóa toàn loader nếu đã đăng ký parallel-capable; dùng instrument/quan sát, tránh khẳng định từ một phép đo thời gian đơn lẻ.
3. **Loader cha và loader con:** API chung phải có cùng Class identity; provider class có thể ở child, API ở parent.
4. **Hai plugin phụ thuộc có hướng:** lớp dùng chung được phân giải đúng theo graph cho phép, không fallback vòng tròn.
5. **Hai thread cùng kích hoạt plugin:** trạng thái registry/lifecycle không tạo thêm khóa vòng hoặc hai lần đăng ký cùng một tài nguyên.
6. **Dừng plugin trong lúc tải:** host xử lý lỗi và cleanup hợp lệ, không đóng dữ liệu nguồn ngay khi một thread còn đang dùng nếu hợp đồng không cho phép.
7. **Lỗi nguồn bytecode/URL/JAR:** các thread chờ khóa được giải phóng qua exception; trạng thái cache vẫn nhất quán, không có luồng treo vô thời hạn.
8. **Class initialization chéo:** test riêng phần <clinit> nếu hệ plugin có static initializer phức tạp; phân biệt lỗi đó với khóa class loader.

Khi viết test mô phỏng deadlock, dùng timeout và cơ chế dọn thread/process; nếu cố tạo deadlock thật nên chạy trong **JVM con** để test có thể kết thúc, tránh làm treo toàn bộ test runner. Dùng CountDownLatch/CyclicBarrier để điều khiển thứ tự thử nghiệm, nhưng không đồng nhất một test có thời gian chờ nhỏ với chứng cứ không có lỗi đồng thời.

Mỗi kiểm thử nên chứng minh một bất biến rõ ràng: define-once theo tên/loader, không có chờ vòng, cấu hình loader không bị bỏ qua, cùng API Class identity và unload/lifecycle đúng điều kiện.

## 12. Các sai lầm thường gặp

1. **Cho rằng synchronized toàn loadClass luôn an toàn hơn:** nó có thể ngăn race cùng tên nhưng cũng chặn mọi tên khác và tạo điều kiện cho deadlock khi ủy quyền chéo.
2. **Gọi registerAsParallelCapable() nhưng quên kiểm tra lớp cha:** đăng ký có thể thất bại nếu một superclass chưa parallel-capable; kiểm tra kết quả và thứ tự khởi tạo lớp.
3. **Gắn cờ parallel-capable nhưng tự bỏ khóa trong override:** vẫn có nguy cơ hai thread gọi defineClass trùng; khóa theo tên là phần cốt lõi của hợp đồng.
4. **Đặt synchronized trên override loadClass:** tiếp tục serialize qua this dù đã đăng ký parallel-capable.
5. **Nhầm lock theo tên với lock theo package/JAR:** hai tên có thể chạy song song nhưng vẫn tranh chấp tài nguyên chung; phải thiết kế cache và I/O thread-safe.
6. **Cho phép plugin loader fallback vòng tròn:** có thể gây đệ quy vô tận hoặc deadlock xuyên thread; quy định một hướng phụ thuộc rõ.
7. **Giữ lock registry/manager khi gọi plugin loader hoặc callback:** vòng chờ có thể hình thành giữa monitor ứng dụng và monitor loader.
8. **Quy lỗi mọi tình huống treo cho ClassLoader:** class initialization, I/O và loader cache có cơ chế chờ khác; xem thread dump trước khi sửa.
9. **Tin rằng timeout sẽ phá được synchronized deadlock:** timeout phía caller không tự giải phóng monitor của một thread đang chờ khóa; cần sửa đồ thị khóa và đường ủy quyền.
10. **Coi parallel-capable là tăng hiệu năng chắc chắn:** việc tải lớp có thể bị giới hạn bởi parent loader, đĩa, ZIP/JAR handling, verification hoặc cache; cần đo trên workload thật.

## 13. Checklist trước khi phát hành class loader dùng cho extension

- **Lớp loader và superclass:** nếu cần parallel-capable, mọi superclass cần thiết đều hỗ trợ; đăng ký từ static initializer của đúng lớp và kiểm tra trả về.
- **Cơ chế khóa:** sử dụng getClassLoadingLock(name) khi viết loadClass, đồng bộ quá trình findLoadedClass → ủy quyền/tìm lớp → resolve; tránh monitor bao ngoài trên this.
- **Định danh lớp:** service API và host API dùng parent-first/shared class identity; không đưa các bản sao API không tương thích vào child-first.
- **Đồ thị phụ thuộc:** không có chu kỳ ủy quyền giữa loader; nếu phải chia sẻ code thì định nghĩa loader sở hữu và thứ tự phân giải cụ thể.
- **Tài nguyên và cache:** mọi dữ liệu dùng trong findClass có hành vi an toàn khi nhiều tên được tải đồng thời; rõ quy tắc về đóng/đổi nguồn bytecode.
- **Vòng đời:** không giữ khóa class loader hoặc plugin registry khi chờ stop/join/callback bên ngoài; có quy trình cleanup/rollback.
- **Chẩn đoán:** log tên lớp, loader identity, đường parent/fallback và thread; có cách thu thread dump ở thời điểm lỗi.
- **Kiểm thử:** cùng tên, khác tên, nhiều loader, plugin reload, lỗi I/O và static initializer đều có kịch bản phù hợp.

**Kết luận kỹ thuật:** ClassLoader phải bảo vệ việc nạp một tên lớp vào cùng loader. Khả năng parallel-capable cho phép các **tên khác nhau** có **khóa nạp lớp khác nhau**; nó giúp giảm tuần tự hóa không cần thiết nhưng không thể tự phá vòng phụ thuộc giữa loader, khóa registry và quá trình khởi tạo lớp. Muốn tránh bế tắc trong runtime extensibility, cần cả **độ mịn của khóa đúng**, **đường ủy quyền không có chu kỳ** và **quản lý vòng đời plugin có kiểm soát**.

**Tham khảo API:** [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html), đặc biệt các thành viên loadClass, getClassLoadingLock và registerAsParallelCapable.