# definePackage, getDefinedPackage và getDefinedPackages trong Java ClassLoader

## 1. Ba API này giải quyết điều gì?

Khi Java nạp các class, một tên như **com.example.plugin.Widget** có hai phần thường dễ nhận thấy:

- **com.example.plugin** là tên package của class.
- **Widget** là tên class bên trong package đó.

Tuy nhiên, package tại runtime **không đơn thuần chỉ là phần đầu của tên class**. JVM và Java API còn gắn package với **class loader đã định nghĩa class**, thông tin phiên bản, nhà cung cấp, package annotations và quy tắc **sealing** nếu có.

Ba API của **java.lang.ClassLoader** giúp làm việc với metadata package do loader định nghĩa:

- **definePackage(...)**: khai báo một đối tượng **java.lang.Package** với tên và metadata cụ thể trong loader đó.
- **getDefinedPackage(name)**: tìm package **được chính loader này định nghĩa**, không tìm sang parent.
- **getDefinedPackages()**: liệt kê các package **do chính loader này định nghĩa**, không gộp package của các ancestor.

Đây là một phần quan trọng khi xây dựng custom ClassLoader, loader đọc JAR/manifest hoặc runtime plugin, đặc biệt khi bạn cần giữ metadata và package identity nhất quán.

**Câu hỏi cốt lõi:** “Package có tên p trong loader A” có phải là “package p trong loader B” không? Câu trả lời là **không nhất thiết**, vì runtime package gắn với **tên package và defining loader**.

## 2. API và visibility chính xác

Các chữ ký liên quan trong Java 17+:

~~~java
// Thuộc java.lang.ClassLoader:
protected Package definePackage(
        String name,
        String specTitle,
        String specVersion,
        String specVendor,
        String implTitle,
        String implVersion,
        String implVendor,
        java.net.URL sealBase);

public final Package getDefinedPackage(String name);

public final Package[] getDefinedPackages();
~~~

Các đoạn trên là **chữ ký API minh họa**, không phải một class chạy độc lập.

| API | Visibility | Kết quả | Ý nghĩa |
| --- | --- | --- | --- |
| **definePackage(...)** | **protected** | Package mới được định nghĩa | Cần gọi từ ClassLoader subclass hoặc nơi có quyền truy cập protected. |
| **getDefinedPackage(name)** | **public final** | Package hoặc null | Chỉ kiểm tra metadata package đã được định nghĩa **ở loader đang gọi**. |
| **getDefinedPackages()** | **public final** | Package[] | Chỉ lấy các packages **ở loader đang gọi**; mảng rỗng nếu chưa định nghĩa package nào. |
| **getPackage(name)** | **protected, deprecated từ Java 9** | Package hoặc null | Có thể tìm package của loader và những ancestor; dễ nhầm ownership. |
| **getPackages()** | **protected** | Package[] | Có thể gồm packages do loader và các ancestor định nghĩa, thậm chí trùng tên. |

**Lưu ý:** **final** ở các phương thức getDefined... có nghĩa subclass không thể override chúng để làm lệch hợp đồng. **definePackage** là protected nên ứng dụng muốn đặt metadata tùy chỉnh thường tạo subclass và gọi nó qua một wrapper.

### 2.1 Chuỗi name là gì?

Với **definePackage/getDefinedPackage**, đối số name là **tên package dạng dấu chấm**, ví dụ:

~~~text
com.example.plugin
org.acme.services
io.sample.internal
~~~

Không dùng đường dẫn resource **com/example/plugin**, không thêm đuôi **.class**, không truyền toàn bộ binary name của một class **com.example.plugin.Widget** khi muốn tìm package **com.example.plugin**.

Đối với ba phương thức này, tên package phải được hiểu tách biệt với **class binary name** mà **loadClass/defineClass** nhận.

## 3. Package nguồn Java và runtime package không hoàn toàn đồng nhất

Trong source:

~~~java
package shop.billing;

public class Invoice {
}
~~~

Khai báo **package shop.billing** giúp compiler tổ chức namespace và kiểm tra quy tắc truy cập, nhưng khi class được JVM định nghĩa, thông tin runtime còn gắn với loader.

~~~text
Source:
  package shop.billing;

Binary class:
  shop.billing.Invoice

Runtime khi định nghĩa:
  (tên package = shop.billing, defining ClassLoader = LoaderA)
~~~

Nếu một **LoaderB** khác định nghĩa class khác cũng thuộc **shop.billing**, các class của hai loader **không tự nằm trong cùng một runtime package** cho kiểm tra quyền truy cập package-private.

Theo JVM Specification, runtime package được nhận diện bằng **tên package và defining loader**. Vì vậy:

~~~text
("shop.billing", LoaderA) != ("shop.billing", LoaderB)
~~~

Dù chuỗi tên package giống nhau, metadata Package có thể khác: phiên bản, vendor, sealing base và annotations.

**Đừng suy luận rằng getDefinedPackage(name) sẽ đi tìm trong classpath hoặc nạp mọi class thuộc package.** Nó chỉ tra các package đã được loader định nghĩa tới thời điểm gọi.

## 4. Khi nào một Package được tạo?

Có hai con đường quan trọng.

### 4.1 Định nghĩa chủ động qua definePackage

Một custom loader có thể **definePackage** trước khi định nghĩa class đầu tiên trong package, nhằm gắn metadata như specification version hoặc code source seal base.

~~~text
Loader riêng
    |
    +-- definePackage("shop.billing", spec/impl/seal metadata)
    |
    +-- findClass("shop.billing.Invoice")
           |
           +-- read bytes
           +-- defineClass(...)
~~~

**Package đã có thể tồn tại trong loader trước cả khi loader định nghĩa một class thuộc package đó.** Định nghĩa Package không đồng nghĩa đã load hoặc initialize class.

### 4.2 Tự động định nghĩa khi defineClass

Javadoc **ClassLoader.defineClass** nêu rằng nếu class mới thuộc một package chưa được loader định nghĩa, **defineClass** sẽ định nghĩa package tương ứng trong loader đó.

Khi package được tạo tự động, metadata được xác định theo quy tắc của **java.lang.Package**. Ví dụ với class trong **unnamed module**, package tự tạo thông thường **không sealed** và các trường specification/implementation title, version, vendor **không được chỉ định**, nên getter có thể trả null.

Điểm quan trọng:

- Nếu muốn **metadata tùy chỉnh**, loader nên gọi **definePackage trước defineClass** cho class đầu tiên trong package.
- Nếu package đã được định nghĩa tự động, một lời gọi definePackage với cùng tên trong cùng loader **không thể dùng để bổ sung hoặc sửa metadata**.
- Khi package đã được tạo, metadata Package **không thể bị định nghĩa lại hoặc chỉnh sửa** qua definePackage.

### 4.3 Package không tự xuất hiện chỉ vì một dòng source

Có thể project chứa hàng trăm file **package shop.billing** nhưng loader cụ thể chưa define bất kỳ class nào thuộc package ấy, cũng chưa gọi definePackage. Khi đó:

~~~java
loader.getDefinedPackage("shop.billing")
~~~

có thể trả **null**, dù bạn nhìn thấy class files trong JAR hoặc IDE.

Ngược lại, **definePackage** có thể làm getDefinedPackage trả non-null dù chưa có class thuộc package đó được nạp.

## 5. definePackage: tám tham số không được nhầm lẫn

Chữ ký đầy đủ:

~~~java
definePackage(
    name,
    specTitle,
    specVersion,
    specVendor,
    implTitle,
    implVersion,
    implVendor,
    sealBase
);
~~~

| Tham số | Vai trò | Ví dụ |
| --- | --- | --- |
| **name** | Tên package có dấu chấm. | **shop.billing** |
| **specTitle** | Tên specification mà package triển khai. | **Billing API** |
| **specVersion** | Phiên bản specification. | **1.2.3** |
| **specVendor** | Tổ chức sở hữu specification. | **Acme Standards** |
| **implTitle** | Tên implementation cụ thể. | **Billing Engine** |
| **implVersion** | Phiên bản implementation. | **build-7** |
| **implVendor** | Tổ chức cung cấp implementation. | **Acme Software** |
| **sealBase** | URL code source mà package được sealed theo đó; null tức không sealed. | **file:/opt/plugins/a.jar** |

Tất cả các thuộc tính specification/implementation kể trên là metadata. Các giá trị như vendor/title thường có thể null khi không cung cấp.

**specVersion và implVersion không cùng mục đích:** một package có thể tuân theo specification **1.2** nhưng implementation được phát hành dưới version **2026.10**. API **Package.isCompatibleWith(version)** liên quan **specification version**, không phải implementation version.

### 5.1 Các getter ở java.lang.Package

Một Package đã được định nghĩa hỗ trợ:

~~~java
p.getName();
p.getSpecificationTitle();
p.getSpecificationVersion();
p.getSpecificationVendor();
p.getImplementationTitle();
p.getImplementationVersion();
p.getImplementationVendor();
p.isSealed();
p.isSealed(url);
p.isCompatibleWith("1.2");
~~~

Đây là trích đoạn lệnh minh họa, không phải các expression statements hợp lệ đứng độc lập trong một method Java. Khi chạy, hãy dùng chúng trong println/assignment hoặc method khác.

**isCompatibleWith** so sánh version specification theo các thành phần số ngăn bởi dấu chấm. Nếu specification version chưa có hoặc chuỗi không hợp lệ, có thể phát sinh **NumberFormatException**. Không dùng phiên bản dạng **build-7** để kiểm tra API này nếu format không thỏa.

## 6. Ví dụ Java 17+ số 1: definePackage thủ công, đọc metadata, ngăn định nghĩa trùng

Tạo file **PackageMetadataDemo.java**:

~~~java
import java.net.URI;
import java.net.URL;

public class PackageMetadataDemo {
    static final class DemoLoader extends ClassLoader {
        DemoLoader(ClassLoader parent) {
            super(parent);
        }

        Package register(String name, URL sealBase) {
            return definePackage(
                    name,
                    "Billing API", "1.2.3", "Acme Standards",
                    "Billing Engine", "build-7", "Acme Software",
                    sealBase);
        }
    }

    public static void main(String[] args) throws Exception {
        DemoLoader loader = new DemoLoader(
                ClassLoader.getPlatformClassLoader());

        System.out.println("count before = "
                + loader.getDefinedPackages().length);

        URL jarA = URI.create("file:/opt/plugins/a.jar").toURL();
        URL jarB = URI.create("file:/opt/plugins/b.jar").toURL();

        Package p = loader.register("shop.billing", jarA);

        System.out.println("name = " + p.getName());
        System.out.println("spec version = "
                + p.getSpecificationVersion());
        System.out.println("implementation = "
                + p.getImplementationTitle());
        System.out.println("sealed = " + p.isSealed());
        System.out.println("sealed at jar A = " + p.isSealed(jarA));
        System.out.println("sealed at jar B = " + p.isSealed(jarB));
        System.out.println("compatible with 1.2 = "
                + p.isCompatibleWith("1.2"));
        System.out.println("same Package = "
                + (p == loader.getDefinedPackage("shop.billing")));
        System.out.println("missing Package = "
                + (loader.getDefinedPackage("shop.missing") == null));
        System.out.println("count after = "
                + loader.getDefinedPackages().length);

        try {
            loader.register("shop.billing", jarA);
            System.out.println("duplicate allowed");
        } catch (IllegalArgumentException expected) {
            System.out.println("duplicate = IllegalArgumentException");
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac PackageMetadataDemo.java
java PackageMetadataDemo
~~~

Stdout dự kiến trên Java 17+:

~~~text
count before = 0
name = shop.billing
spec version = 1.2.3
implementation = Billing Engine
sealed = true
sealed at jar A = true
sealed at jar B = false
compatible with 1.2 = true
same Package = true
missing Package = true
count after = 1
duplicate = IllegalArgumentException
~~~

### 6.1 Giải thích

**DemoLoader** là loader mới chưa tự define class/package nào. Class chứa mã DemoLoader thuộc loader của chương trình gọi, không phải do object DemoLoader vừa tạo định nghĩa. Vì vậy trước lời register đầu tiên, **getDefinedPackages().length** ở loader đó là 0.

**register** gọi protected definePackage từ subclass, cho phép code main thêm package với metadata.

**isSealed** chỉ kiểm tra metadata Package đã lưu. Đối tượng URL jarA là seal base nên isSealed(jarA) true; URL khác jarB false.

**getDefinedPackage("shop.billing")** trả đúng object Package được tạo trước đó. Đọc getter không làm loader nạp class Invoice hoặc tự động mở JAR.

**register cùng tên lần nữa** ném **IllegalArgumentException**, vì một loader không thể definePackage trùng tên, bất kể metadata mới giống hay khác. Muốn thay metadata trong cùng loader sau khi package đã được tạo là quá muộn.

### 6.2 Cảnh báo: metadata sealing không tự làm loader an toàn

Bài demo chỉ gọi **definePackage**, chưa define class từ JAR. **Package.isSealed() == true** cho biết metadata nói package sealed. Nó **không chứng minh mọi custom ClassLoader sẽ tự động kiểm tra URL nguồn JAR** với sealBase trong mọi đường defineClass. Loader triển khai việc đọc JAR/manifest và định nghĩa class phải tôn trọng kiểm tra sealing thích hợp. Các loader JAR tiêu chuẩn có logic tương ứng.

Đừng sử dụng definePackage như công cụ sandbox đối với bytecode không tin cậy.

## 7. getDefinedPackage(name): chỉ nhìn package của chính loader

Chữ ký:

~~~java
public final Package getDefinedPackage(String name);
~~~

Đặc điểm quan trọng:

- Trả **Package** do **loader đang gọi** đã định nghĩa.
- Trả **null** nếu loader này chưa định nghĩa package có tên tương ứng.
- Truyền **null** làm name gây **NullPointerException**.
- **Không** tự nạp class, tìm resource hay hỏi parent để lấy Package.
- Không cần package đó hiện có instance object hay class đang initialized.
- Nếu package đã được define trước đó, trả metadata hiện có của loader.

Ví dụ:

~~~java
Package own = childLoader.getDefinedPackage("api.common");
~~~

Nếu class **api.common.Service** được parent loader định nghĩa và child chỉ delegate để dùng class ấy, phương thức trên vẫn có thể trả **null**: package thuộc **parent**, không thuộc child.

**Đừng đánh đồng initiating loader với defining loader.** Child có thể gọi loadClass và nhận Class do parent định nghĩa; điều đó không tạo Package tương ứng trong child.

## 8. getDefinedPackages(): liệt kê chính xác local definitions

Chữ ký:

~~~java
public final Package[] getDefinedPackages();
~~~

Hợp đồng:

- Trả về **một mảng** các đối tượng Package do loader này định nghĩa.
- **Không** tự gộp package của parent hoặc ancestor.
- Không có **hai Package cùng tên** trong mảng trả về của một loader.
- Trả **mảng độ dài 0** nếu loader chưa define package nào.
- Không nên dựa vào **thứ tự** của các phần tử vì API không cam kết ordering phù hợp để sắp xếp nghiệp vụ.

Ví dụ xử lý kết quả:

~~~java
Package[] ownPackages = loader.getDefinedPackages();

for (Package p : ownPackages) {
    System.out.println(p.getName()
            + " : " + p.getSpecificationVersion());
}
~~~

Đây là snippet đặt trong method có biến loader. Nếu cần xuất báo cáo ổn định, hãy **sort bằng getName()** trước khi in; không suy diễn rằng thứ tự được trả bằng thứ tự đã load hoặc thứ tự file JAR.

### 8.1 getDefinedPackages không có nghĩa là toàn bộ packages tồn tại trong JVM

Một Java process có thể chứa hàng trăm loader, các modules và các JAR khác nhau. **getDefinedPackages trên một loader chỉ là góc nhìn local**, không phải registry toàn JVM. Để kiểm tra class thực sự đến từ loader nào, dùng **clazz.getClassLoader()** kết hợp metadata/package của Class phù hợp.

## 9. Đối chiếu với getPackage và getPackages cũ

Hai API khác có thể gây nhầm:

~~~java
// Trong ClassLoader subclass:
protected Package getPackage(String name);
protected Package[] getPackages();
~~~

**getPackage(name)** được **deprecated từ Java 9**. Nó tìm trong chính loader và sau đó tìm ancestor nếu chưa thấy. Trong các loader có thể định nghĩa cùng tên package, hành vi trả package từ parent có thể làm metadata/annotations không phản ánh package do child sẽ định nghĩa.

**getPackages()** cũng lấy packages được định nghĩa bởi loader và ancestors. Mảng kết quả **có thể có hai Package cùng tên** nếu parent và child mỗi loader tự define tên đó.

Điều này khác với getDefinedPackages: mảng local không chứa tên trùng.

| API | Phạm vi | Có thể thấy package parent? | Ghi chú |
| --- | --- | --- | --- |
| **getDefinedPackage("p")** | Chỉ loader hiện tại | Không | Public final; ưu tiên khi cần package ownership chính xác. |
| **getDefinedPackages()** | Chỉ loader hiện tại | Không | Public final; không trùng tên trong một loader. |
| **getPackage("p")** | Loader và ancestors | Có | Protected và deprecated từ Java 9. |
| **getPackages()** | Loader và ancestors | Có | Protected; có thể trả nhiều Package tên giống nhưng khác owner. |

**Không nên dùng getPackage để quyết định rằng “package đã được child định nghĩa”.** Nó có thể chỉ phát hiện package ở parent.

## 10. Ví dụ Java 17+ số 2: package cùng tên ở parent và child

Ví dụ tự định nghĩa metadata Package ở hai loader khác nhau, không cần tạo class files, nhằm chứng minh phạm vi các API.

Tạo file **PackageScopeDemo.java**:

~~~java
public class PackageScopeDemo {
    static final class PackageLoader extends ClassLoader {
        PackageLoader(ClassLoader parent) {
            super(parent);
        }

        Package add(String name, String version) {
            return definePackage(
                    name, "Shared API", version, "Acme",
                    "Runtime", "1", "Acme", null);
        }

        @SuppressWarnings("deprecation")
        Package legacyLookup(String name) {
            return getPackage(name);
        }

        int visiblePackageMatches(String name) {
            int count = 0;
            for (Package p : getPackages()) {
                if (name.equals(p.getName())) {
                    count++;
                }
            }
            return count;
        }
    }

    public static void main(String[] args) {
        PackageLoader parent = new PackageLoader(
                ClassLoader.getPlatformClassLoader());
        PackageLoader child = new PackageLoader(parent);

        Package parentPackage = parent.add("demo.shared", "1.0");

        System.out.println("child local before = "
                + (child.getDefinedPackage("demo.shared") == null));
        System.out.println("legacy found parent = "
                + (child.legacyLookup("demo.shared") == parentPackage));
        System.out.println("visible matches before = "
                + child.visiblePackageMatches("demo.shared"));

        Package childPackage = child.add("demo.shared", "2.0");

        System.out.println("child version = "
                + child.getDefinedPackage("demo.shared")
                        .getSpecificationVersion());
        System.out.println("same Package object = "
                + (childPackage == parentPackage));
        System.out.println("visible matches after = "
                + child.visiblePackageMatches("demo.shared"));
        System.out.println("child local count = "
                + child.getDefinedPackages().length);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac PackageScopeDemo.java
java PackageScopeDemo
~~~

Stdout dự kiến:

~~~text
child local before = true
legacy found parent = true
visible matches before = 1
child version = 2.0
same Package object = false
visible matches after = 2
child local count = 1
~~~

### 10.1 Vì sao cùng package name không gây IllegalArgumentException?

Quy tắc không cho definePackage trùng tên áp dụng **trong cùng một loader**. Parent và child là **hai đối tượng ClassLoader khác nhau**, vì vậy mỗi loader có thể định nghĩa Package cùng tên **demo.shared**.

Trong ví dụ:

~~~text
PackageLoader parent
    +-- demo.shared, specVersion 1.0

PackageLoader child (parent là loader phía trên)
    +-- demo.shared, specVersion 2.0
~~~

**child.getDefinedPackage("demo.shared")** ban đầu null dù parent đã có package. **legacyLookup** tìm lên parent nên thấy Package cũ. Sau khi child tự define, local Package được trả về, và getPackages có thể đưa ra cả hai Package cùng tên.

**Thực tế quan trọng:** demo chỉ định nghĩa Package metadata, chưa định nghĩa class nào dưới hai package đó. Việc Java cho hai loader giữ Package cùng tên **không có nghĩa bạn nên chia shared interface/DTO qua hai defining loaders**. Runtime package identity và class identity có thể trở thành vấn đề khi code cần tương tác qua loader boundary.

## 11. Ví dụ Java 17+ số 3: defineClass tự tạo Package khi chưa được define

Bây giờ quan sát một package xuất hiện **tự động**, không gọi definePackage bằng tay.

Cấu trúc:

~~~text
project/
├── AutoPackageDemo.java
└── plugin-src/
    └── lab/
        └── auto/
            └── Marker.java
~~~

**plugin-src/lab/auto/Marker.java**:

~~~java
package lab.auto;

public class Marker {
    public String value() {
        return "ready";
    }
}
~~~

**AutoPackageDemo.java**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class AutoPackageDemo {
    static final class ByteLoader extends ClassLoader {
        private final Path root;

        ByteLoader(Path root) {
            super(ClassLoader.getPlatformClassLoader());
            this.root = root;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            try {
                byte[] bytes = Files.readAllBytes(
                        root.resolve(name.replace('.', '/') + ".class"));
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ByteLoader loader = new ByteLoader(Path.of("plugin-out"));

        System.out.println("before = "
                + (loader.getDefinedPackage("lab.auto") == null));

        Class<?> type = loader.loadClass("lab.auto.Marker");
        Package p = loader.getDefinedPackage("lab.auto");

        System.out.println("after name = " + p.getName());
        System.out.println("spec version null = "
                + (p.getSpecificationVersion() == null));
        System.out.println("sealed = " + p.isSealed());
        System.out.println("defined by loader = "
                + (type.getClassLoader() == loader));
        System.out.println("defined count = "
                + loader.getDefinedPackages().length);

        Class<?> base = loader.loadClass("java.lang.String");
        System.out.println("bootstrap class = "
                + (base.getClassLoader() == null));
        System.out.println("java.lang locally defined = "
                + (loader.getDefinedPackage("java.lang") != null));
    }
}
~~~

Biên dịch từ thư mục **project**:

~~~bash
javac -d plugin-out plugin-src/lab/auto/Marker.java
javac AutoPackageDemo.java
java AutoPackageDemo
~~~

Stdout dự kiến trong classpath và loader setup này:

~~~text
before = true
after name = lab.auto
spec version null = true
sealed = false
defined by loader = true
defined count = 1
bootstrap class = true
java.lang locally defined = false
~~~

### 11.1 Phân tích

- Lúc đầu ByteLoader chưa define class hoặc package lab.auto, nên getDefinedPackage trả null.
- Parent (platform loader) không thấy lab.auto.Marker trong plugin-out; loader riêng gọi findClass, đọc bytes rồi defineClass.
- Vì chưa có package lab.auto trong loader, **defineClass tự tạo Package** với metadata mặc định cho unnamed module.
- **getDefinedPackages().length == 1** phản ánh package local mới được tạo.
- Loader có thể initiate class java.lang.String bằng delegation nhưng **không định nghĩa** package java.lang. Vì vậy getDefinedPackage("java.lang") vẫn null.

**Lưu ý môi trường:** Không đưa plugin-out lên một classpath mà parent trong ví dụ thấy được lab.auto.Marker; nếu không, lớp có thể do parent định nghĩa và output khác.

### 11.2 Sửa metadata sau khi tự động định nghĩa có được không?

Nếu sau **loader.loadClass("lab.auto.Marker")** bạn gọi **definePackage("lab.auto", ...)** qua subclass, thao tác sẽ ném IllegalArgumentException vì package local đã có.

Muốn set version/seal metadata của package trong custom loader, hãy thực hiện trước class đầu tiên được define ở package đó. Nếu nạp từ JAR tiêu chuẩn, sử dụng loader hiểu manifest thay vì tự làm sai metadata.

## 12. Package sealing là gì?

**Package sealing** là quy tắc package/JAR có thể giới hạn nguồn code cho các class thuộc cùng package. Khi một package sealed với một code source URL, các class được loader nạp vào package đó phải tuân thủ nguồn phù hợp theo hợp đồng loader/JAR.

~~~text
Package demo.internal
    sealed với URL: file:/plugins/a.jar
            |
            +-- class từ a.jar: phù hợp
            |
            +-- class từ b.jar: sealing violation nếu loader enforce
~~~

JAR Manifest có thể chứa:

~~~text
Manifest-Version: 1.0
Sealed: true
~~~

Hoặc override sealing cho package qua manifest entry, ví dụ:

~~~text
Name: demo/internal/
Sealed: true
~~~

**Package.isSealed()** cho biết metadata package sealed hay không; **Package.isSealed(URL)** kiểm tra có sealed đối với code source URL được truyền không.

### 12.1 Phân biệt package sealing và sealed classes của Java 17

Đây là hai cơ chế khác nhau:

| Package sealing | Sealed class/interface |
| --- | --- |
| Thuộc package/JAR và code source, thể hiện ở Package metadata. | Thuộc hệ kiểu Java, dùng **sealed**, **permits** và subclass restrictions. |
| Gắn với nguồn định nghĩa các class trong package. | Kiểm soát những class được phép extends/implements class/interface. |
| Thông thường liên quan loader đọc JAR manifest. | Được compiler/JVM kiểm tra qua định nghĩa kiểu. |
| API tiêu biểu: Package.isSealed(). | Cú pháp sealed class, Class.isSealed(), Class.getPermittedSubclasses(). |

Một package sealed không có nghĩa mọi class trong nó là sealed class; một sealed class có thể nằm trong package không sealed.

### 12.2 Cảnh báo khi tự xây custom loader

**definePackage** gắn metadata sealing, nhưng việc **enforce sealing trên nhiều code sources** cần loader nạp JAR áp dụng đúng kiểm tra. **URLClassLoader/JAR class loaders tiêu chuẩn** có logic đọc manifest và kiểm tra sealing. Đừng chỉ gọi definePackage rồi kết luận mọi nguồn bytes đã được xác minh.

Nếu bạn tự đọc bytes và gọi defineClass, cần xem xét code source, protection domain, chứng chỉ, package rules và kiểm tra sealing phù hợp. Đừng bắt SecurityException rồi coi như ClassNotFoundException.

## 13. Metadata manifest và thứ tự tải class

Trong JAR, metadata package thường được đọc từ **META-INF/MANIFEST.MF**. Các thuộc tính như Specification-Title, Specification-Version, Implementation-Version và Sealed có thể xuất hiện ở main attributes hoặc sections cho từng package.

Ví dụ mô tả manifest:

~~~text
Manifest-Version: 1.0
Implementation-Title: Billing Engine
Implementation-Version: 3.4.1

Name: shop/billing/
Specification-Title: Billing API
Specification-Version: 1.2.3
Sealed: true
~~~

Nếu nhiều JAR chứa class trong cùng package do một loader define, **thứ tự class/package được define đầu tiên** có thể ảnh hưởng metadata package được ghi nhận. Đó là lý do các plugin cần tránh split packages ngoài ý muốn và không trông cậy getDefinedPackage như bảng hợp nhất metadata nhiều JAR.

**Package metadata không được tự động cập nhật** khi class thứ hai trong cùng package đến từ JAR khác. Nếu metadata đã tạo trước đó, loader phải tôn trọng trạng thái package hiện hữu và kiểm tra sealing phù hợp.

### 13.1 Đừng suy từ Package ra chính xác JAR chứa mọi class

Package là metadata của runtime package, **không phải bản đồ cho từng class file** hoặc một lệnh quét JAR. Để điều tra Class được định nghĩa từ đâu, kiểm tra defining loader, **ProtectionDomain/CodeSource** khi có và các công cụ logging/JAR listing phù hợp.

## 14. Named modules có khác unnamed module không?

Từ Java 9, module system ảnh hưởng cách package được tạo:

- Với **classes trong unnamed module**, một Package tự động được define thường không sealed và không có specification/implementation metadata trừ khi loader đặt chủ động.
- Với **classes trong named module**, Package có quy tắc tự động riêng; package có thể được sealed theo module location nếu biết được, metadata specification/implementation title/version/vendor thường unspecified.
- Javadoc **khuyến nghị mạnh không gọi definePackage thủ công cho packages của named modules**, mà để việc defineClass tạo package theo module rules.
- Nếu vẫn có lý do thực sự phải define thủ công, phải bảo đảm các Package objects trong module có properties nhất quán với quy tắc Package; ví dụ không được gán sai seal base.

**Đừng coi tên module thay thế defining loader trong mọi khái niệm.** Module membership còn ảnh hưởng exports/opens/readability, trong khi package identity runtime vẫn liên hệ với loader, và Package API diễn tả metadata theo quy tắc của class/module tương ứng.

## 15. Package.getPackage và Package.getPackages có nên dùng không?

Một số tài liệu cũ còn đề cập static methods trên java.lang.Package:

~~~java
Package.getPackage("shop.billing");
Package.getPackages();
~~~

Các API legacy này có ngữ nghĩa theo loader của caller và có thể gây nhầm trong môi trường nhiều loaders. Từ Java 9 chúng được **deprecated** để hướng sang những API phản ánh owner rõ hơn.

Khi đã biết loader mà bạn đang khảo sát, ưu tiên:

~~~java
ClassLoader loader = SomeClass.class.getClassLoader();
Package p = loader.getDefinedPackage("shop.billing");
Package[] own = loader.getDefinedPackages();
~~~

Đây là snippet; cần có SomeClass cụ thể và lưu ý **Class.getClassLoader() có thể trả null** với bootstrap-defined class, nên phải xử lý null trước khi gọi loader methods.

Khi có một Class cụ thể, cũng có thể dùng **SomeClass.class.getPackage()** để nhận Package liên quan tới class đó. Cách này thường sát ý định hơn khi hỏi “package runtime của chính class này có metadata gì?”, thay vì hỏi “loader A đã define package cùng tên chưa?”.

## 16. Quy trình chẩn đoán lỗi

### 16.1 getDefinedPackage(name) trả null dù source có package

Kiểm tra:

1. Bạn đang gọi đúng **defining loader** của class chưa?
2. Package đã được loader này define qua definePackage hoặc defineClass chưa?
3. Class được parent định nghĩa vì parent-first delegation phải không?
4. Chuỗi package name có dùng dấu chấm và đúng case không?
5. Code có nhầm getDefinedPackage với lệnh tìm package trong classpath không?

Nếu class được parent define, getDefinedPackage trên child không tự thấy package của parent.

### 16.2 definePackage ném IllegalArgumentException

Package cùng tên **đã được định nghĩa trong chính loader đó**. Có thể defineClass trước đó đã tự tạo package, hoặc code đã definePackage thủ công.

**Cách khắc phục:** đưa việc đăng ký metadata lên trước defineClass, kiểm tra getDefinedPackage nếu cần, đồng bộ lifecycle khi nhiều threads nạp class. Không retry vô hạn với metadata mới vì package không thể định nghĩa lại.

### 16.3 SecurityException liên quan sealing/certificates

Kiểm tra nguồn code, JAR manifest, sealBase và package đã được định nghĩa trước. Một loader đọc nhiều JAR có split package sealed có thể gặp sealing violation. Đồng thời, ClassLoader.defineClass có ràng buộc certificate set giữa các class trong cùng package.

Đừng xử lý mọi lỗi này như chỉ là ClassNotFoundException; lỗi package integrity cần được điều tra riêng.

### 16.4 Metadata Package khác với manifest bạn vừa xem

Có thể loader đã định nghĩa package từ một JAR hoặc class trước đó. Package không tự viết lại metadata mỗi khi nạp class mới.

Kiểm tra classpath/JAR order, parent delegation, named/unnamed module và loader thực sự định nghĩa class. Không mặc định Manifest-Version là specification version: đó là hai khái niệm riêng.

### 16.5 ClassCastException hoặc IllegalAccessError giữa các loader

Nếu hai loaders định nghĩa class cùng name hoặc package cùng name, chúng có thể không cùng runtime type/package. Để kiểm tra:

~~~java
System.out.println(a.getName().equals(b.getName()));
System.out.println(a == b);
System.out.println(a.getClassLoader());
System.out.println(b.getClassLoader());
~~~

Đoạn trên là snippet có sẵn hai Class objects a và b. Cùng string name nhưng Class khác có thể giải thích lỗi cast. Package-private access còn bị chi phối bởi runtime package identity, không chỉ source package statement.

## 17. Những hiểu nhầm cần tránh

- **“definePackage tạo mọi class của package.”** Sai: nó tạo Package metadata; defineClass mới tạo runtime class.
- **“getDefinedPackages quét hết classpath.”** Sai: chỉ trả các package loader này đã định nghĩa.
- **“Child.getDefinedPackage thấy package của parent.”** Sai: không delegation trong API này.
- **“getPackage và getDefinedPackage giống nhau.”** Sai: getPackage legacy có thể tìm ancestor.
- **“Hai loaders cùng tên package phải dùng chung một Package.”** Sai: mỗi defining loader có thể định nghĩa package cùng tên riêng.
- **“Có Package object nghĩa là đã initialized class nào đó.”** Sai: có thể definePackage trước khi có class.
- **“Package metadata sửa được bằng definePackage gọi lại.”** Sai: trùng tên trong cùng loader ném IllegalArgumentException.
- **“isSealed=true làm custom loader luôn chống mọi nguồn bytecode khác.”** Không đủ: loader phải thực thi quy tắc integrity/sealing đúng.
- **“Sealed package là sealed class.”** Sai: hai cơ chế độc lập.
- **“Một JAR khác vào sau cập nhật version của Package.”** Không: metadata đã xác lập không được tự động ghi đè.
- **“Package owner chỉ là tên package.”** Sai: runtime package còn gắn defining loader.
- **“Named module nên luôn definePackage thủ công.”** Sai: Javadoc khuyên để tự động định nghĩa.

## 18. Bài tập tự kiểm tra

**Câu 1.** Custom loader chưa định nghĩa class nào; gọi definePackage("app.core", ...) có làm getDefinedPackage("app.core") trả non-null không?

**Trả lời:** Có. definePackage tạo Package metadata riêng trong loader trước khi defineClass.

**Câu 2.** Sau khi defineClass tự tạo package app.core, có thể gọi definePackage cùng tên để thêm version không?

**Trả lời:** Không. Package đã được định nghĩa; definePackage trùng tên trong cùng loader ném IllegalArgumentException.

**Câu 3.** Child loader delegate loadClass("api.Service") cho parent và nhận Class của parent. Child.getDefinedPackage("api") có bắt buộc non-null không?

**Trả lời:** Không. Child chỉ initiate class qua delegation, còn parent define class/package.

**Câu 4.** getDefinedPackages và getPackages khác gì trong loader có parent?

**Trả lời:** getDefinedPackages chỉ liệt kê packages do loader hiện tại định nghĩa; getPackages còn có thể liệt kê packages của ancestors và tên trùng.

**Câu 5.** Hai loader A và B cùng definePackage("p.q", ...). Đây có phải hành vi không hợp lệ chỉ vì trùng tên?

**Trả lời:** Không. Quy tắc unique áp dụng trong mỗi loader. Hai runtime packages có thể cùng tên nhưng owner khác nhau.

**Câu 6.** isSealed(url) trả true có nghĩa gì?

**Trả lời:** Package metadata ghi package sealed với sealBase URL tương ứng; việc loader enforce sealing khi nạp code sources cần đúng hợp đồng của implementation.

**Câu 7.** Package.getSpecificationVersion() khác getImplementationVersion() như thế nào?

**Trả lời:** Một cái ghi version của specification, cái còn lại ghi phiên bản implementation cụ thể.

**Câu 8.** getDefinedPackages có đảm bảo thứ tự tương ứng JAR classpath không?

**Trả lời:** Không. Nếu muốn output ổn định, sort theo getName.

**Câu 9.** Vì sao Javadoc không khuyến khích definePackage thủ công trong named modules?

**Trả lời:** Module có quy tắc định nghĩa Package tự động riêng, kể cả sealing base/metadata; tự đặt tay có thể tạo thông tin không nhất quán.

**Câu 10.** Có thể dùng definePackage để sửa quyền package-private giữa hai ClassLoaders có cùng tên package không?

**Trả lời:** Không. Runtime package identity còn dựa trên defining loader; metadata không biến hai runtime packages thành một.

## 19. Ghi nhớ

~~~text
ClassLoader L
    |
    +-- definePackage("p.q", metadata)
    |      -> tạo Package local, trước khi defineClass
    |
    +-- defineClass("p.q.Foo", bytes)
    |      -> tự define Package local nếu chưa có
    |
    +-- getDefinedPackage("p.q")
    |      -> chỉ lấy Package do L định nghĩa
    |
    +-- getDefinedPackages()
           -> toàn bộ Package local của L

Parent packages KHÔNG tự nằm trong getDefinedPackages(L).
Runtime package identity còn gắn với defining loader.
~~~

**Nguyên tắc quan trọng nhất:** dùng **definePackage** để thiết lập metadata trước khi class đầu tiên trong package được define; dùng **getDefinedPackage/getDefinedPackages** để kiểm tra đúng ownership local của loader. Không dùng các API này như trình quét classpath, không đánh đồng package name với runtime package identity, và lưu ý sealing/metadata/module khi thiết kế class loader đọc JAR.

### Nguồn tham khảo chính thức

- **ClassLoader API, Java SE 21** — definePackage/getDefinedPackage/getDefinedPackages/getPackage/getPackages: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html
- **Package API, Java SE 21** — metadata, sealing, versioning và module behavior: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Package.html
- **JAR File Specification, Java SE 21 — Package Sealing:** https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html
- **JVMS §5.3, Creation and Loading:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3
