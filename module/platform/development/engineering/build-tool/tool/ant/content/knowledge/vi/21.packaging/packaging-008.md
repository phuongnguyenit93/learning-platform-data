# Vai trò của EAR trong hệ thống Java EE hoặc Jakarta EE hiện hữu

EAR (Enterprise Archive) là định dạng gói triển khai dùng để gom nhiều thành phần của một ứng dụng doanh nghiệp Java vào một đơn vị. Trong hệ thống Java EE hoặc Jakarta EE hiện hữu, EAR thường đóng vai trò là gói cấp ứng dụng: nó chứa các module như web application, EJB, connector và các thư viện dùng chung, kèm metadata mô tả cách các module thuộc cùng một ứng dụng.

Khi làm việc với một hệ thống đang chạy trên application server, cần hiểu EAR trong mối quan hệ với toàn bộ kiến trúc triển khai. EAR không phải một loại mã nguồn Java riêng và cũng không thay thế WAR hoặc JAR. Nó là lớp đóng gói ở cấp ứng dụng, giúp application server nhận biết và triển khai một tập hợp module như một ứng dụng doanh nghiệp thống nhất.

Với Apache Ant, task <ear> có thể tạo gói EAR từ các module đã được build. Ant chịu trách nhiệm tập hợp và đóng gói tệp; việc nạp module, quản lý component, cấp tài nguyên và thực thi ứng dụng thuộc về application server tương thích với nền tảng Java EE hoặc Jakarta EE mà dự án sử dụng.

## 1. EAR nằm ở đâu trong kiến trúc Java EE/Jakarta EE?

Một hệ thống Java doanh nghiệp có thể gồm nhiều lớp:

- Web layer: giao diện HTTP, servlet, JSP hoặc các framework web chạy trong web container.
- Business layer: xử lý nghiệp vụ, có thể dùng EJB hoặc các thành phần Java khác.
- Integration layer: kết nối hệ thống bên ngoài, ví dụ resource adapter theo JCA hoặc thư viện tích hợp.
- Persistence layer: truy cập cơ sở dữ liệu, transaction và các dịch vụ liên quan.
- Shared libraries: các thư viện được nhiều module trong cùng ứng dụng sử dụng.

Các thành phần này có thể được đóng gói thành các artifact riêng:

| Artifact | Vai trò |
|---|---|
| JAR | Thư viện Java, EJB module hoặc application client module tùy nội dung và metadata |
| WAR | Web application, chứa tài nguyên web, lớp và thư viện dành cho web module |
| RAR | Resource adapter đóng gói theo Java Connector Architecture |
| EAR | Gói cấp ứng dụng, tập hợp nhiều module và thư viện dùng chung |

Ví dụ, một hệ thống bán hàng có thể có:

~~~text
Sales platform
   |
   +-- portal.war
   |     +-- trang web và REST/Servlet endpoints
   |
   +-- sales-services.jar
   |     +-- EJB hoặc các thành phần nghiệp vụ
   |
   +-- messaging-adapter.rar
   |     +-- resource adapter kết nối hệ thống nhắn tin
   |
   +-- lib/
         +-- shared-domain.jar
         +-- common-logging.jar
~~~

Các module trên có thể được đóng gói trong một tệp sales-platform.ear. Application server triển khai EAR và quản lý các module theo cấu hình, chuẩn nền tảng và chính sách của máy chủ.

Không phải mọi ứng dụng Java đều cần EAR. Một web application độc lập có thể chỉ cần WAR. EAR hữu ích khi ứng dụng có nhiều module cần được quản lý như một đơn vị, cần metadata cấp ứng dụng hoặc đang tuân theo kiến trúc triển khai enterprise hiện có.

## 2. EAR giải quyết vấn đề gì trong hệ thống hiện hữu?

### 2.1. Gom nhiều module thành một đơn vị triển khai

Trong hệ thống lớn, các thành phần thường được phát triển hoặc build riêng. Portal có thể do nhóm web quản lý, EJB module do nhóm nghiệp vụ phát triển, còn connector do nhóm tích hợp phụ trách.

Nếu mỗi module được triển khai hoàn toàn độc lập, người vận hành phải quản lý nhiều artifact và nhiều thao tác triển khai. EAR cho phép tập hợp các module liên quan thành một gói cấp ứng dụng.

Điều này giúp:

- Phát hành một phiên bản ứng dụng chứa các module tương thích với nhau.
- Quản lý metadata ở cấp ứng dụng.
- Triển khai hoặc gỡ bỏ ứng dụng theo đơn vị mà application server hỗ trợ.
- Giảm nguy cơ một số module được cập nhật còn module khác vẫn dùng phiên bản cũ.
- Lưu dấu phiên bản artifact cấp ứng dụng trong quy trình release.

Việc triển khai EAR như một đơn vị không có nghĩa mọi application server đều cập nhật tất cả module theo cùng một cách nội bộ. Cơ chế deploy, rollback, rolling update và trạng thái module vẫn phụ thuộc sản phẩm server.

### 2.2. Chia ranh giới trách nhiệm giữa các module

Mỗi module vẫn có cấu trúc và metadata riêng. WAR có thể chứa web.xml, EJB JAR có thể chứa descriptor riêng, RAR có metadata connector, còn EAR có application.xml ở cấp ứng dụng.

Sự phân chia này giúp nhóm quản lý thành phần theo trách nhiệm mà vẫn có một artifact tổng hợp. Khi thay đổi một module, có thể build lại module đó rồi tạo lại EAR chứa phiên bản module mới cùng các thành phần còn lại.

Cần lưu ý rằng các module trong EAR vẫn có quan hệ phụ thuộc. Nếu portal.war gọi API trong sales-services.jar, phiên bản của hai module phải tương thích. Việc chỉ gom các tệp vào một EAR không tự giải quyết xung đột API hoặc dependency.

### 2.3. Chia sẻ thư viện ở cấp ứng dụng

EAR có thể chứa các thư viện dùng chung trong thư mục library directory, thường là lib. Các module trong ứng dụng có thể nhìn thấy thư viện cấp ứng dụng theo quy tắc classloading của nền tảng và application server.

Ví dụ:

~~~text
sales-platform.ear
├── META-INF/
│   └── application.xml
├── portal.war
├── sales-services.jar
└── lib/
    ├── shared-domain.jar
    └── common-logging.jar
~~~

Cách tổ chức này có thể giảm việc đóng gói lặp cùng một thư viện trong nhiều module. Tuy nhiên, khả năng nhìn thấy và thứ tự ưu tiên classloader còn phụ thuộc nền tảng, phiên bản server và cấu hình riêng. Không nên coi EAR lib là một classpath toàn cục không có giới hạn.

## 3. Cấu trúc bên trong một EAR

EAR là một archive dựa trên định dạng ZIP. Bên trong có thể chứa các module triển khai, thư viện cấp ứng dụng và thư mục metadata META-INF.

Ví dụ cấu trúc:

~~~text
sales-platform.ear
├── META-INF/
│   ├── application.xml
│   └── MANIFEST.MF
├── portal.war
├── sales-services.jar
├── messaging-adapter.rar
└── lib/
    ├── shared-domain.jar
    └── common-logging.jar
~~~

Các thành phần:

- META-INF/application.xml: deployment descriptor cấp ứng dụng nếu dự án sử dụng descriptor này.
- META-INF/MANIFEST.MF: manifest của EAR, có thể chứa metadata bổ sung.
- portal.war: web module.
- sales-services.jar: EJB module hoặc module Java EE/Jakarta EE dạng JAR phù hợp.
- messaging-adapter.rar: resource adapter module.
- lib/: thư mục thư viện dùng chung ở cấp ứng dụng nếu được cấu hình và hỗ trợ.

Không phải mọi EAR đều cần tất cả loại module. Một EAR đơn giản có thể chỉ chứa WAR và một vài thư viện dùng chung. Một số phiên bản nền tảng cho phép application server phát hiện module mà không cần application.xml tường minh trong một số trường hợp; tuy vậy, hệ thống hiện hữu thường có descriptor vì cần khai báo context root, thứ tự khởi tạo hoặc metadata cấp ứng dụng.

### 3.1. Thư mục META-INF

META-INF nằm ở gốc EAR và chứa metadata cấp ứng dụng. application.xml là deployment descriptor chính theo chuẩn khi được sử dụng.

Không đặt application.xml bên trong WAR hoặc EJB JAR nếu mục đích là mô tả toàn bộ EAR. Mỗi module có thể có descriptor riêng ở vị trí tương ứng, còn descriptor EAR mô tả quan hệ và metadata cấp ứng dụng.

### 3.2. Các module nằm ở gốc EAR

Các module WAR, EJB JAR và RAR thường được đặt ở gốc EAR. Tên tệp trong application.xml phải khớp với đường dẫn module thực tế trong archive.

Ví dụ, nếu descriptor khai báo portal.war nhưng Ant đóng gói web-portal.war, application server có thể không tìm thấy module được khai báo. Hãy đồng bộ tên module giữa build file và descriptor.

### 3.3. Thư mục lib

Theo quy ước Java EE/Jakarta EE, thư viện dùng chung của ứng dụng thường được đặt trong thư mục lib ở gốc EAR. Descriptor application.xml có thể khai báo library-directory nếu dự án muốn dùng tên thư mục khác. Nếu không cấu hình khác, lib là thư mục mặc định trong mô hình này.

Các JAR trong lib là thư viện hỗ trợ module, không phải module triển khai độc lập cần khai báo như WAR hoặc EJB module. Không đưa các JAR công cụ build, JUnit hoặc API của application server vào đây trừ khi ứng dụng thực sự cần chúng và việc đóng gói phù hợp với nền tảng.

## 4. Vai trò của application.xml

### 4.1. Deployment descriptor cấp ứng dụng

application.xml mô tả các module trong EAR và một số metadata cấp ứng dụng. Trong hệ thống hiện hữu, descriptor có thể xác định:

- Tên hiển thị của ứng dụng.
- Danh sách module và tên archive tương ứng.
- Context root của web module.
- Thư mục thư viện cấp ứng dụng.
- Một số metadata khác được chuẩn nền tảng hỗ trợ, tùy phiên bản.

Ví dụ descriptor Java EE 8 với một web module và một EJB module:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<application xmlns="http://xmlns.jcp.org/xml/ns/javaee"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://xmlns.jcp.org/xml/ns/javaee http://xmlns.jcp.org/xml/ns/javaee/application_8.xsd"
             version="8">

    <display-name>Sales Platform</display-name>

    <module>
        <web>
            <web-uri>portal.war</web-uri>
            <context-root>/sales</context-root>
        </web>
    </module>

    <module>
        <ejb>sales-services.jar</ejb>
    </module>

    <library-directory>lib</library-directory>
</application>
~~~

Trong ví dụ:

- display-name là tên hiển thị của ứng dụng.
- web-uri chỉ tên WAR nằm trong EAR.
- context-root đặt đường dẫn gốc mà web module được truy cập.
- ejb chỉ tên EJB JAR trong EAR.
- library-directory chỉ thư mục chứa thư viện cấp ứng dụng.

Descriptor phải phù hợp với phiên bản Java EE mà application server hỗ trợ. Không dùng schema Java EE 8 chỉ vì nó là ví dụ nếu hệ thống đang chạy nền tảng khác.

### 4.2. Khi nào application.xml cần thiết?

Mức độ bắt buộc của application.xml phụ thuộc phiên bản nền tảng, kiểu ứng dụng và metadata mà hệ thống cần khai báo. Một số nền tảng có thể phát hiện module theo cấu trúc archive hoặc descriptor của module. Tuy nhiên, trong hệ thống enterprise hiện hữu, descriptor tường minh thường hữu ích khi:

- Cần đặt context root cụ thể cho WAR.
- Cần khai báo rõ danh sách module.
- Cần cấu hình thư mục library khác mặc định.
- Cần giữ metadata cấp ứng dụng nhất quán giữa các môi trường.
- Quy trình triển khai hoặc công cụ quản trị dựa vào descriptor.

Nếu xóa application.xml khỏi một EAR cũ, đừng giả định server sẽ tự tạo lại mọi metadata giống hệt. Hãy kiểm tra cách ứng dụng đang được triển khai, cấu hình context root, tên module và các descriptor vendor-specific trước khi thay đổi.

## 5. Java EE và Jakarta EE: chọn đúng thế hệ nền tảng

### 5.1. Tên gọi và namespace

Java EE được chuyển giao cho Eclipse Foundation và phát triển dưới tên Jakarta EE. Từ Jakarta EE 9, nhiều API enterprise chuyển namespace từ javax.* sang jakarta.*. Việc chuyển đổi namespace này ảnh hưởng đến mã nguồn, dependency, descriptor và môi trường triển khai.

Ví dụ:

| Thế hệ | Ví dụ namespace API |
|---|---|
| Java EE 7/8 | javax.servlet, javax.ejb, javax.persistence |
| Jakarta EE 9 trở lên | jakarta.servlet, jakarta.ejb, jakarta.persistence |

Không phải mọi package bắt đầu bằng javax đều chuyển thành jakarta. Một số API thuộc Java SE hoặc các chuẩn khác vẫn giữ namespace riêng. Khi di chuyển hệ thống, cần dựa vào danh sách API của nền tảng và dependency thực tế, không thay chuỗi javax thành jakarta một cách máy móc.

### 5.2. Descriptor cũng phải tương thích

application.xml của Java EE và Jakarta EE sử dụng namespace/schema theo phiên bản tương ứng. Ví dụ Jakarta EE 10:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<application xmlns="https://jakarta.ee/xml/ns/jakartaee"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="https://jakarta.ee/xml/ns/jakartaee https://jakarta.ee/xml/ns/jakartaee/application_10.xsd"
             version="10">

    <display-name>Sales Platform</display-name>

    <module>
        <web>
            <web-uri>portal.war</web-uri>
            <context-root>/sales</context-root>
        </web>
    </module>

    <module>
        <ejb>sales-services.jar</ejb>
    </module>

    <library-directory>lib</library-directory>
</application>
~~~

Đây là descriptor dành cho môi trường hỗ trợ Jakarta EE 10. Không thể chỉ đổi namespace trong application.xml rồi coi toàn bộ ứng dụng Java EE cũ đã được chuyển đổi. Các module bên trong EAR, thư viện bên thứ ba, server runtime và cấu hình triển khai cũng phải tương thích.

### 5.3. Không trộn module thuộc hai thế hệ API

Một EAR thường cần được xây dựng cho một nền tảng và application server cụ thể. Nếu một WAR sử dụng javax.servlet còn một module khác sử dụng jakarta.servlet, chúng có thể không tương thích trong cùng môi trường server.

Trước khi đóng gói, xác định:

- Phiên bản Java EE hoặc Jakarta EE mục tiêu.
- Phiên bản JDK được application server hỗ trợ.
- Phiên bản API mà từng module compile against.
- Phiên bản thư viện bên thứ ba.
- Namespace trong descriptor.
- Các descriptor riêng của application server.

Với hệ thống cũ, hãy duy trì một bộ toolchain và dependency đã biết là tương thích trước khi lên kế hoạch chuyển đổi Jakarta EE.

## 6. Classloading và thư viện dùng chung trong EAR

### 6.1. Phạm vi của thư viện cấp ứng dụng

Thư viện đặt trong EAR lib thường được cung cấp cho các module thuộc cùng ứng dụng theo mô hình classloading của nền tảng. Điều này hữu ích khi nhiều module cần dùng chung domain model, utility hoặc thư viện logging.

Ví dụ:

~~~text
application.ear
├── portal.war
├── billing.jar
├── reporting.jar
└── lib/
    ├── shared-model.jar
    └── common-utils.jar
~~~

portal.war, billing.jar và reporting.jar có thể cần cùng kiểu dữ liệu từ shared-model.jar. Đặt thư viện ở cấp EAR có thể giúp tránh đóng gói nhiều bản trùng trong từng module.

Tuy nhiên, application server có thể áp dụng classloader riêng cho EAR, từng module hoặc cấu hình isolation đặc thù. Hãy đọc tài liệu của server đang sử dụng trước khi dựa vào một giả định cụ thể về thứ tự nạp lớp hoặc khả năng chia sẻ.

### 6.2. Tránh đóng gói trùng thư viện

Nếu cùng một JAR xuất hiện trong EAR lib và trong WEB-INF/lib của WAR, ứng dụng có thể gặp xung đột hoặc nạp các lớp không như dự kiến. Hậu quả có thể gồm:

- ClassCastException dù hai đối tượng có cùng tên lớp.
- NoSuchMethodError khi module nạp phiên bản API khác với phiên bản lúc biên dịch.
- LinkageError do lớp hoặc method không tương thích.
- Hành vi khác nhau giữa các application server.

Nên lập danh sách thư viện dùng chung và thư viện riêng của từng module. Một dependency chỉ nên được đặt ở một vị trí có chủ đích, trừ khi server hoặc module yêu cầu cách đóng gói đặc biệt.

### 6.3. Không đóng gói API do application server cung cấp một cách tùy tiện

Các API chuẩn như Servlet, EJB, JPA hoặc Jakarta REST thường được application server cung cấp. Nếu đóng gói bản API khác vào EAR lib hoặc WEB-INF/lib, có thể gây xung đột classloader hoặc vi phạm mô hình triển khai.

Trong build Ant, hãy tách thư viện dùng lúc biên dịch khỏi thư viện cần đóng gói:

- API do server cung cấp có thể cần trên compile classpath.
- Khi package EAR, không đưa các API container-provided vào lib nếu runtime đã cung cấp chúng.
- Dependency triển khai thực sự của ứng dụng cần được đóng gói đúng nơi theo kiến trúc và chính sách server.

Không nên lấy toàn bộ JAR từ compile classpath rồi copy vào EAR. Compile classpath có thể chứa Ant, test framework, API container và công cụ chỉ cần lúc build.

## 7. Vai trò của EAR trong các loại module

### 7.1. Web module: WAR

WAR chứa thành phần web như servlet, filter, listener, tài nguyên tĩnh, JSP và thư viện web. Trong EAR, WAR là một module con.

application.xml có thể khai báo context root cho WAR. Nếu không có descriptor hoặc context root không được chỉ định, application server có thể dùng quy tắc mặc định theo tên module hoặc cấu hình riêng.

Không đặt WAR bên trong một thư mục tùy ý rồi quên cập nhật web-uri. Tên module trong descriptor phải trỏ tới đúng đường dẫn bên trong EAR.

### 7.2. EJB module: JAR

EJB module thường được đóng gói thành JAR. Nó chứa lớp enterprise bean và metadata cần thiết. Module này có thể cung cấp nghiệp vụ cho web module hoặc module khác trong cùng ứng dụng.

Không phải mọi JAR trong EAR đều là EJB module. Một JAR utility nằm trong lib thường chỉ là thư viện dùng chung. Descriptor application.xml cần khai báo đúng module type cho EJB JAR nếu descriptor liệt kê module.

### 7.3. Connector module: RAR

RAR là resource adapter archive dùng cho tích hợp hệ thống theo Java Connector Architecture. Ví dụ có thể kết nối với hệ thống ERP, messaging provider hoặc hệ thống doanh nghiệp khác.

Việc đưa RAR vào EAR không tự cấu hình connection factory, credential, resource binding hoặc endpoint của application server. Những thông tin này thường cần cấu hình tại server hoặc thông qua descriptor phù hợp.

### 7.4. Application client module

Một số ứng dụng enterprise có application client module được đóng gói thành JAR. Hỗ trợ và cách vận hành application client phụ thuộc phiên bản nền tảng và sản phẩm server. Nếu hệ thống cũ sử dụng loại module này, hãy giữ cấu hình và công cụ client tương thích khi build EAR.

## 8. Đóng gói EAR bằng Apache Ant

### 8.1. Task ear của Ant

Ant cung cấp task <ear> để tạo Enterprise Archive. Task nhận đường dẫn đầu ra, application descriptor và các tập hợp tệp cần đưa vào archive.

Ví dụ:

~~~xml
<ear destfile="dist/sales-platform.ear"
     appxml="src/ear/META-INF/application.xml">
    <fileset dir="build/modules">
        <include name="portal.war" />
        <include name="sales-services.jar" />
        <include name="messaging-adapter.rar" />
    </fileset>

    <lib dir="lib/ear"
         includes="*.jar" />
</ear>
~~~

Trong ví dụ:

- destfile là EAR được tạo.
- appxml chỉ tới application.xml sẽ được đặt trong META-INF của EAR.
- fileset chọn các module đã build.
- lib đưa các JAR thư viện vào library directory của EAR.

Thư mục build/modules chỉ nên chứa các module triển khai. Thư mục lib/ear chỉ nên chứa thư viện cấp ứng dụng đã được chọn. Không dùng một fileset quá rộng trỏ vào toàn bộ workspace vì có thể đưa cả file tạm, JAR test hoặc output cũ vào EAR.

### 8.2. Tách target build module và target đóng gói

EAR nên được tạo sau khi tất cả module thành phần đã build thành công. Có thể tổ chức target theo dependency:

~~~xml
<project name="sales-platform" default="ear" basedir=".">

    <property name="build.dir" location="${basedir}/build" />
    <property name="modules.dir" location="${build.dir}/modules" />
    <property name="dist.dir" location="${basedir}/dist" />

    <target name="prepare">
        <mkdir dir="${modules.dir}" />
        <mkdir dir="${dist.dir}" />
    </target>

    <target name="build-web" depends="prepare">
        <!-- Gọi build của web module và đặt portal.war vào modules.dir -->
    </target>

    <target name="build-ejb" depends="prepare">
        <!-- Gọi build của EJB module và đặt sales-services.jar vào modules.dir -->
    </target>

    <target name="build-adapter" depends="prepare">
        <!-- Gọi build của connector và đặt messaging-adapter.rar vào modules.dir -->
    </target>

    <target name="ear"
            depends="build-web,build-ejb,build-adapter">
        <ear destfile="${dist.dir}/sales-platform.ear"
             appxml="${basedir}/src/ear/META-INF/application.xml">
            <fileset dir="${modules.dir}">
                <include name="portal.war" />
                <include name="sales-services.jar" />
                <include name="messaging-adapter.rar" />
            </fileset>
            <lib dir="${basedir}/lib/ear"
                 includes="*.jar" />
        </ear>
    </target>

</project>
~~~

Các phần comment đại diện cho target hoặc task build module thực tế. Nếu module được build bởi build file khác, có thể gọi Ant sub-build bằng task ant hoặc dùng cơ chế điều phối hiện có của repository.

Target ear chỉ đóng gói sau khi ba target thành phần hoàn tất. Ant không tự biết module nào phải được build; dependency giữa target phải được khai báo rõ.

### 8.3. Tạo EAR không đồng nghĩa với deploy

Task <ear> tạo file archive. Nó không cài đặt ứng dụng vào application server, không khởi tạo EJB, không tạo datasource và không kiểm tra mọi resource binding.

Sau khi build, EAR thường được chuyển cho quy trình deploy riêng. Tùy server, việc triển khai có thể qua giao diện quản trị, CLI, deployment API hoặc thư mục auto-deploy. Không nên gắn thông tin đăng nhập quản trị server vào build file dùng chung nếu quy trình phát hành có thể tách bước đóng gói và triển khai.

## 9. Giữ EAR tương thích với application server hiện hữu

### 9.1. Xác định server và phiên bản nền tảng

Trước khi thay đổi cấu trúc EAR, cần biết ứng dụng đang chạy trên application server nào và server hỗ trợ phiên bản Java EE/Jakarta EE nào.

Các yếu tố phải khớp:

- Phiên bản Java EE hoặc Jakarta EE mà EAR khai báo.
- Phiên bản JDK mà application server hỗ trợ.
- Phiên bản module descriptor và deployment descriptor.
- API được dùng trong WAR, EJB JAR và RAR.
- Các thư viện do server cung cấp.
- Vendor-specific descriptor và classloading policy.

Một EAR có thể được tạo thành công về mặt ZIP nhưng vẫn bị server từ chối triển khai vì descriptor không hợp lệ, module không tương thích hoặc dependency thiếu.

### 9.2. Giữ vendor descriptor nếu hệ thống cần

Một số application server sử dụng descriptor riêng để cấu hình classloading, resource reference, security role, context root hoặc deployment behavior. Các tệp này có thể nằm trong META-INF của EAR hoặc trong thư mục metadata của module tùy sản phẩm.

Nếu hệ thống hiện hữu đang dùng vendor descriptor, không xóa chúng chỉ vì application.xml đã có. Hãy xác định tệp nào thuộc chuẩn portable và tệp nào chỉ dành cho server cụ thể. Khi thay server hoặc nâng phiên bản, cần chuyển đổi các descriptor riêng theo tài liệu của nhà cung cấp.

Ví dụ tên tệp vendor-specific khác nhau theo sản phẩm; không nên sao chép một descriptor từ server này sang server khác và kỳ vọng nó được hiểu giống nhau.

### 9.3. Kiểm tra context root và tên module

Context root có thể được khai báo trong application.xml hoặc descriptor riêng của server. Nếu cả hai nơi cùng cấu hình, quy tắc ưu tiên phụ thuộc application server.

Khi đổi tên WAR, cần cập nhật mọi tham chiếu liên quan. Khi đổi context root, kiểm tra cấu hình reverse proxy, URL bên ngoài, health check, security constraint và các ứng dụng khác gọi endpoint đó.

## 10. EAR và chiến lược nâng cấp Jakarta EE

Một hệ thống Java EE cũ có thể cần tiếp tục vận hành trong khi từng module được nâng cấp. EAR là ranh giới đóng gói hữu ích, nhưng không tự tạo ra tính tương thích giữa hai thế hệ API.

Một kế hoạch chuyển đổi nên xem xét:

1. Xác định nền tảng Java EE hiện tại và application server.
2. Liệt kê các module trong EAR và dependency của từng module.
3. Xác định API javax.* nào cần chuyển sang jakarta.*.
4. Kiểm tra thư viện bên thứ ba có bản hỗ trợ Jakarta EE tương ứng.
5. Kiểm tra descriptor XML và schema version.
6. Chọn application server hỗ trợ Jakarta EE mục tiêu.
7. Build từng module bằng JDK và API tương thích.
8. Tạo EAR với descriptor và thư viện đúng thế hệ.
9. Deploy vào môi trường thử nghiệm và chạy integration test.
10. Kiểm tra transaction, security, JNDI, datasource, messaging và classloading trước khi phát hành.

Không nên đổi namespace trong một module rồi đóng gói cùng các module cũ mà chưa xác minh khả năng tương thích. Một EAR chứa module Java EE và Jakarta EE có thể gặp vấn đề về API và classloading tùy server; hãy coi việc chuyển đổi là một dự án tương thích có kiểm thử, không phải thay đổi tên package đơn giản.

## 11. Kiểm tra nội dung EAR trước khi deploy

Sau khi Ant tạo EAR, có thể kiểm tra archive bằng công cụ jar hoặc unzip.

Ví dụ:

~~~text
jar tf dist/sales-platform.ear
~~~

Kết quả mong đợi có thể tương tự:

~~~text
META-INF/
META-INF/application.xml
portal.war
sales-services.jar
messaging-adapter.rar
lib/shared-domain.jar
lib/common-logging.jar
~~~

Kiểm tra các điểm:

- application.xml có ở META-INF của EAR hay không nếu dự án yêu cầu descriptor.
- Tên module trong descriptor có đúng với tệp thực tế không.
- Tất cả module bắt buộc có mặt.
- Thư viện dùng chung nằm trong đúng library directory.
- Không có JUnit, Ant tool hoặc tệp build tạm bị đưa vào archive.
- Không có hai phiên bản xung đột của cùng thư viện.
- Vendor descriptor cần thiết vẫn được giữ.
- Không có secret hoặc cấu hình môi trường riêng bị đóng gói nhầm.

Việc liệt kê archive chỉ xác nhận cấu trúc tệp. Để xác nhận EAR thực sự deploy được, phải triển khai lên application server tương thích và kiểm tra log khởi động cùng chức năng ứng dụng.

## 12. Các lỗi thường gặp khi làm việc với EAR

| Biểu hiện | Nguyên nhân có thể xảy ra | Hướng xử lý |
|---|---|---|
| Server không tìm thấy module | Tên trong application.xml không khớp tên archive | Đồng bộ web-uri/ejb/connector với tên file trong EAR |
| WAR deploy nhưng URL sai | Context root khác cấu hình mong muốn | Kiểm tra application.xml và descriptor riêng của server |
| EAR được tạo nhưng deploy thất bại | Descriptor sai schema hoặc module không tương thích | Kiểm tra phiên bản Java EE/Jakarta EE và server |
| Module không tìm thấy thư viện dùng chung | JAR đặt sai thư mục hoặc classloading policy không như giả định | Kiểm tra library-directory và quy tắc classloader của server |
| ClassCastException hoặc NoSuchMethodError | Nhiều phiên bản cùng một thư viện hoặc classloader isolation | Loại bản trùng, thống nhất dependency và kiểm tra classloader |
| API javax/jakarta không tương thích | Module được build cho các thế hệ nền tảng khác nhau | Chọn một target platform và dependency tương thích |
| Ant tạo EAR thiếu module | Target build module chưa được nối vào dependency của target ear | Khai báo depends và kiểm tra thư mục staging |
| EAR chứa JAR test hoặc công cụ build | Fileset đóng gói quá rộng | Giới hạn include và tách thư mục module khỏi thư viện công cụ |
| Server từ chối RAR | Thiếu cấu hình resource adapter hoặc server không hỗ trợ phiên bản connector | Kiểm tra JCA version, RAR metadata và cấu hình server |
| EAR deploy được nhưng chức năng tích hợp lỗi | Datasource, JNDI, security hoặc messaging chưa được cấu hình | Kiểm tra tài nguyên và binding tại application server |

Khi xử lý lỗi, hãy phân biệt lỗi tạo archive với lỗi triển khai. Nếu file EAR không chứa module, sửa Ant build. Nếu archive đúng nhưng server không khởi tạo module, kiểm tra descriptor, API và cấu hình application server.

## 13. Khi nào nên giữ EAR và khi nào có thể đơn giản hóa?

Giữ EAR khi:

- Ứng dụng hiện hữu đang được triển khai và vận hành theo mô hình enterprise archive.
- Có nhiều module WAR, EJB, RAR hoặc application client cần cùng vòng đời phát hành.
- Cần metadata cấp ứng dụng hoặc thư viện dùng chung.
- Quy trình vận hành, quản trị và rollback dựa vào artifact EAR.
- Application server yêu cầu hoặc dự án đã chuẩn hóa cấu trúc EAR.

Có thể cân nhắc chỉ phát hành WAR hoặc JAR độc lập khi:

- Ứng dụng thực chất chỉ có một web module.
- Không dùng metadata cấp ứng dụng hoặc các module enterprise khác.
- Application server hỗ trợ triển khai artifact độc lập.
- Quy trình release và vận hành đã được điều chỉnh tương ứng.
- Việc thay đổi không phá vỡ các dependency, URL, security hoặc deployment script hiện có.

Không nên bỏ EAR chỉ vì một WAR có thể chạy độc lập. Trước khi thay đổi, hãy kiểm kê module, descriptor, classloading, shared library và các bước vận hành đang phụ thuộc vào gói hiện tại.

## 14. Checklist khi build và duy trì EAR bằng Ant

- [ ] Đã xác định application server và phiên bản Java EE/Jakarta EE mục tiêu.
- [ ] Đã xác định các module WAR, EJB JAR, RAR hoặc application client cần đóng gói.
- [ ] Đã build thành công từng module trước target EAR.
- [ ] Đã xác định application.xml có cần thiết và phải dùng schema version nào.
- [ ] Đã đồng bộ tên module trong descriptor với tên archive thực tế.
- [ ] Đã xác định thư mục lib và các thư viện dùng chung.
- [ ] Đã loại dependency chỉ dành cho Ant, test hoặc compiler khỏi EAR.
- [ ] Đã kiểm tra không có nhiều phiên bản xung đột của cùng thư viện.
- [ ] Đã giữ các vendor descriptor mà hệ thống hiện hữu cần.
- [ ] Đã kiểm tra cấu trúc EAR bằng jar tf hoặc công cụ archive tương đương.
- [ ] Đã deploy thử trên application server tương thích.
- [ ] Đã kiểm tra datasource, JNDI, transaction, security, messaging và context root.
- [ ] Đã chạy integration test trên môi trường gần với production.

## 15. Nguyên tắc duy trì

- Coi EAR là đơn vị đóng gói cấp ứng dụng, còn WAR/JAR/RAR là các module hoặc thành phần bên trong.
- Dùng EAR khi kiến trúc và quy trình vận hành hiện hữu cần nhiều module được quản lý cùng nhau.
- Giữ application.xml và tên module đồng bộ với archive thực tế.
- Chọn descriptor và API đúng thế hệ Java EE hoặc Jakarta EE.
- Quản lý thư viện cấp EAR có chủ đích và tránh đóng gói trùng.
- Không đưa API do application server cung cấp vào EAR một cách tùy tiện.
- Giữ vendor descriptor nếu deployment hiện tại phụ thuộc vào chúng.
- Dùng Ant để tập hợp và đóng gói; dùng application server hoặc công cụ quản trị để triển khai.
- Kiểm tra archive trước, sau đó deploy thử để xác nhận tính tương thích thực tế.
- Không chuyển đổi Java EE sang Jakarta EE chỉ bằng cách sửa namespace descriptor; cần nâng cấp module, dependency và runtime cùng nhau.

EAR giúp một hệ thống Java EE/Jakarta EE nhiều module được phát hành và quản lý như một ứng dụng doanh nghiệp thống nhất. Khi hiểu rõ vai trò của descriptor, module, thư viện dùng chung và application server, build Ant có thể tạo ra archive phù hợp với kiến trúc hiện hữu mà vẫn giữ được ranh giới rõ ràng giữa đóng gói và triển khai.

