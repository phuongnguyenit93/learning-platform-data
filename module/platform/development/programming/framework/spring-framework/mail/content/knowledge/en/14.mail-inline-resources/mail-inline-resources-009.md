# Classpath Paths and Resources Inside JARs in Spring Framework Mail

When an email needs logos, banners, illustrations, or sample documents packaged with the application, those files typically live in `src/main/resources`. When running from an IDE, developers can inadvertently treat these files as filesystem files. However, once the application is packaged as a JAR, resources may reside **inside an archive or a nested JAR**, no longer existing as standalone files with ordinary filesystem paths.

Spring provides the `Resource` abstraction to read resources from various sources: classpath, filesystem, URLs, byte arrays, and more. In Spring Framework Mail, `MimeMessageHelper` accepts `Resource` or `InputStreamSource`, making it possible to attach images and documents from the classpath even when the application runs from a JAR.

The key point is: **a classpath path is a resource name searched by the class loader, not a directory path on disk**. For resources inside a JAR, read them via `getInputStream()` or pass the `Resource` directly to the mail helper. Never assume a resource can always be converted to a `File` via `getFile()`.

## 1. What is the classpath?

The classpath is the set of directories and archives the Java runtime uses to locate classes and resources. When running from an IDE, the classpath typically includes output directories such as `target/classes` or `build/resources/main. When packaged, those same resources are normally bundled into the JAR.

Example project layout:

~~~text
my-mail-app/
├── src/
│   └── main/
│       ├── java/
│       │   └── com/example/mail/
│       │       └── NotificationService.java
│       └── resources/
│           └── mail/
│               ├── images/
│               │   ├── logo.png
│               │   └── banner.jpg
│               └── documents/
│                   └── terms.pdf
└── pom.xml
~~~

Files under `src/main/resources` are copied by the build tool into the classpath output. When running from the classes directory, the resource may appear at:

~~~text
target/classes/mail/images/logo.png
~~~

When packaged as a regular JAR, the entry may be:

~~~text
mail/images/logo.png
~~~

With an executable Spring Boot JAR, application classes and resources typically reside under `BOOT-INF/classes/` inside the archive. The Spring Boot loader sets up a class loader capable of reading resources from this packaging structure.

In Java code, resource paths start from the **classpath root**, so you typically use:

~~~text
mail/images/logo.png
~~~

Do not include the project's source directory prefix:

~~~text
src/main/resources/mail/images/logo.png
~~~

That is a development-time source path, not the resource name on the classpath.

### Resources in a JAR are not regular files

A JAR is a ZIP-structured archive. A resource inside a JAR is an archive entry. The class loader knows how to find and read that entry, but the operating system does not necessarily expose a standalone file path for it.

~~~text
When running from an IDE:
  classpath -> target/classes/
                  |
                  +--> mail/images/logo.png

When running from a JAR:
  classpath -> application.jar
                  |
                  +--> mail/images/logo.png

When running an executable Spring Boot JAR:
  application.jar
      |
      +--> BOOT-INF/classes/mail/images/logo.png
      |
      +--> BOOT-INF/lib/dependency.jar
                 |
                 +--> dependency resources
~~~

The logical path `mail/images/logo.png` stays identical across environments, while physical storage differs.

## 2. Placing resources in src/main/resources

With Maven or Gradle, the standard location for runtime resources is `src/main/resources`. Example:

~~~text
src/main/resources/
└── mail/
    ├── images/
    │   ├── logo.png
    │   └── banner.jpg
    └── documents/
        └── terms.pdf
~~~

After building, the application can reference `mail/images/logo.png`, `mail/images/banner.jpg`, and `mail/documents/terms.pdf`.

Example:

~~~java
new ClassPathResource("mail/images/logo.png");
~~~

Do not use:

~~~java
new ClassPathResource(
    "src/main/resources/mail/images/logo.png"
);
~~~

Because `src/main/resources` is the source directory placed onto the classpath by the build tool; it is not part of the final resource name.

### Watch out for letter casing

Windows typically uses a case-insensitive filesystem by default, whereas entry names inside a JAR are case-sensitive. For instance, if the actual file is `mail/images/Logo.png` while code requests `mail/images/logo.png`, it may work on a Windows developer machine yet fail when run from a JAR on Linux. Always match exact spelling and casing of resources.

## 3. Using ClassPathResource

`ClassPathResource` is Spring's `Resource` implementation for reading resources from the classpath.

~~~java
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

Resource logo =
    new ClassPathResource("mail/images/logo.png");
~~~

You can check the resource:

~~~java
if (!logo.exists()) {
    throw new IllegalStateException("Email logo was not found");
}

if (!logo.isReadable()) {
    throw new IllegalStateException("Email logo is not readable");
}
~~~

Common methods:

| Method | Meaning |
| --- | --- |
| `exists()` | Checks whether the resource exists in the current source |
| `isReadable()` | Checks whether the resource is readable according to the implementation |
| `getInputStream()` | Opens a stream to read the content |
| `getURL()` | Returns a URL if the resource can be represented as a URL |
| `getURI()` | Returns a URI if representable |
| `getFile()` | Returns a File if the resource corresponds to a filesystem file |
| `contentLength()` | Returns the content size if the implementation can determine it |

For resources inside a JAR, `exists()` and `getInputStream()` are the appropriate operations. `getFile()` can fail because a JAR entry is not a standalone file.

### Reading a resource with InputStream

~~~java
import java.io.IOException;
import java.io.InputStream;
import org.springframework.core.io.ClassPathResource;

ClassPathResource resource =
    new ClassPathResource("mail/images/logo.png");

try (InputStream input = resource.getInputStream()) {
    byte[] buffer = new byte[8192];

    int read;
    while ((read = input.read(buffer)) != -1) {
        // Process each chunk of data.
    }
}
~~~

`getInputStream()` works through the class loader and does not require the resource to be extracted as a regular file. Remember to close the stream with try-with-resources.

### Choosing a ClassLoader or Class

`ClassPathResource` can be constructed with a path and class loader:

~~~java
ClassPathResource resource = new ClassPathResource(
    "mail/images/logo.png",
    Thread.currentThread().getContextClassLoader()
);
~~~

Or using a class as the reference point:

~~~java
ClassPathResource resource =
    new ClassPathResource("/mail/images/logo.png", NotificationService.class);
~~~

Using a class as reference resolves relative to that class; relative paths may be resolved from the class's package. If you want a path from the classpath root, use the appropriate absolute form or use the constructor accepting a class loader with a resource name without a leading slash.

In typical Spring applications, `new ClassPathResource("mail/images/logo.png")` is clear enough. When an application uses multiple class loaders, plugins, or special container environments, specify which class loader should locate the resource.

## 4. Using ResourceLoader in a Spring application

`ResourceLoader` is Spring's abstraction for obtaining a resource from a location string. It is useful when you want to configure the resource source via configuration rather than instantiating an implementation directly.

~~~java
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Service;

@Service
public class MailAssetService {

    private final ResourceLoader resourceLoader;

    public MailAssetService(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public Resource getLogo() {
        return resourceLoader.getResource(
            "classpath:mail/images/logo.png"
        );
    }
}
~~~

The `classpath:` prefix tells Spring to look up the resource on the classpath.

Common prefixes:

| Location | Meaning |
| --- | --- |
| `classpath:mail/logo.png` | Resource on the classpath |
| `file:/opt/app/mail/logo.png` | Resource from the filesystem via a file URL |
| `https://cdn.example.com/logo.png` | Resource from an HTTP/HTTPS URL |
| `/opt/app/mail/logo.png` | May be handled differently depending on implementation/context; use an explicit prefix to avoid ambiguity |

When reading a fixed resource packaged with the application, `classpath:` is straightforward. When reading a file managed outside the JAR that can change without rebuilding the application, use filesystem configuration or dedicated storage.

### ResourceLoader does not support all classpath patterns

`ResourceLoader#getResource(...)` is suited for a single specific location. If you need to match multiple resources using wildcards such as `classpath*:mail/**/*.png`, use `ResourcePatternResolver`. The `classpath*:` prefix searches multiple locations across the classpath and dependency JARs; do not assume every `ResourceLoader` implementation handles that pattern as expected.

## 5. Using ResourcePatternResolver to locate multiple resources

Some emails may need to attach multiple sample documents or pick images from a directory. `PathMatchingResourcePatternResolver` supports pattern matching:

~~~java
import java.io.IOException;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.core.io.support.ResourcePatternResolver;

ResourcePatternResolver resolver =
    new PathMatchingResourcePatternResolver();

Resource[] templates = resolver.getResources(
    "classpath*:mail/templates/**/*.html"
);

for (Resource template : templates) {
    System.out.println(template.getDescription());
}
~~~

Distinctions:

- `classpath:...` generally locates a resource at a single classpath location.
- `classpath*:...` searches all matching resources across the classpath, potentially spanning multiple directories and dependency JARs.
- `**` and `*` are patterns interpreted by the resolver, not ordinary file path syntax.

If you only need a logo with a fixed name, no pattern resolver is needed. If scanning across multiple plugins or resources contributed by several modules, `classpath*:` can be helpful.

### Notes when scanning resources inside JARs

Pattern matching over JARs can depend on how the resolver and class loader expose URLs. For simple patterns, Spring handles many common cases; however, never design an application assuming every archive or custom class loader supports every filesystem-style wildcard.

When the resource list is critical configuration, use an explicit manifest/catalog or test against the actual packaged artifact.

## 6. Why does getFile() often fail when a resource is inside a JAR?

A common mistake:

~~~java
ClassPathResource resource =
    new ClassPathResource("mail/images/logo.png");

File file = resource.getFile();
~~~

When running from an IDE, the resource may live under `target/classes`, so `getFile()` can return a real file. When running from a JAR, the resource may be an archive entry with no standalone file path. In that case, Spring cannot represent it as a `java.io.File` and may throw `FileNotFoundException`.

Code that seems to work in development yet breaks in deployment:

~~~text
IDE:
  target/classes/mail/images/logo.png
  -> can map to a File

Executable JAR:
  app.jar!/BOOT-INF/classes/mail/images/logo.png
  -> archive entry, not a regular File
~~~

### Do not convert a JAR URL to a File by slicing strings

Some code attempts:

~~~java
String path = resource.getURL().getPath();
File file = new File(path);
~~~

This approach is unreliable. URLs may use varying protocols or archive formats, contain percent-encoded characters, include archive separators, or come from specialized class loaders. Converting an archive URL into a File via manual string slicing ties code to packaging internals.

**If an API accepts Resource or InputStreamSource, pass the resource directly.** If a real filesystem file is genuinely required, copy the stream to a lifecycle-managed temporary file.

### getURL() is still useful, but it is not a File

`getURL()` can return a URL representing the resource, such as a JAR URL or a launcher-specific URL. You can open a stream from a URL if needed, but never assume the protocol is always `file:`, that the URL converts straight into a `Path`, or that the URL string follows a fixed format. Use the `Resource` API instead of manually parsing URL strings.

## 7. Attaching classpath images in emails with MimeMessageHelper

For logo images packaged with the application, there is no need to convert the resource into a File. `MimeMessageHelper` accepts `Resource` directly:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailer {

    private final JavaMailSender mailSender;

    public WelcomeMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient)
            throws MessagingException {

        Resource logo =
            new ClassPathResource("mail/images/logo.png");

        if (!logo.exists() || !logo.isReadable()) {
            throw new IllegalStateException(
                "Classpath email logo is missing or unreadable");
        }

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
            "UTF-8"
        );

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Welcome");

        String html = """
            <html lang="en">
              <body>
                <img src="cid:brandLogo"
                     width="120"
                     alt="Example">
                <h1>Welcome!</h1>
                <p>Your account is ready.</p>
              </body>
            </html>
            """;

        helper.setText(html, true);

        // Add inline resources after setting the text/HTML body.
        helper.addInline("brandLogo", logo, "image/png");

        mailSender.send(message);
    }
}
~~~

Points to note:

- The path `mail/images/logo.png` is relative to the classpath root.
- `Resource` can read the resource even when it resides inside a JAR.
- `addInline` takes `brandLogo` as the Content-ID.
- HTML references it with `cid:brandLogo`.
- The content type is declared as `image/png`; use the MIME type matching the actual file.
- `setText(html, true)` marks the body as HTML.
- Call `addInline` after setting the body as recommended by Spring to ensure the MIME structure is constructed properly.

Content-ID is an identifier inside the message, not a classpath path. You can name it `brandLogo`, `headerBanner`, or `productImage-123`, as long as it is unique within the email and matches the `cid:...` string in HTML.

### Sending both plain text and HTML

If the email needs a plain-text fallback, use the `setText(plainText, htmlText)` overload:

~~~java
String plainText = """
    Hello!

    Your account has been created.
    """;

String htmlText = """
    <html>
      <body>
        <img src="cid:brandLogo" alt="Example">
        <h1>Hello!</h1>
        <p>Your account has been created.</p>
      </body>
    </html>
    """;

helper.setText(plainText, htmlText);
helper.addInline("brandLogo", logo, "image/png");
~~~

The multipart mode constructor in the example above supports the MIME structure needed for content and related resources. The text and HTML versions represent the same message in two presentation formats.

## 8. Attaching documents inside a JAR

Resources inside a JAR can also be used as attachments, such as terms of service or PDF documents shipped with the application:

~~~java
Resource terms =
    new ClassPathResource("mail/documents/terms.pdf");

if (!terms.exists() || !terms.isReadable()) {
    throw new IllegalStateException(
        "Terms document is not available");
}

helper.addAttachment("terms-and-conditions.pdf", terms);
~~~

No call to `terms.getFile()` is needed. The helper reads the resource through the stream abstraction.

Full example:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper =
    new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("support@example.com");
helper.setTo(recipient);
helper.setSubject("User Guide");
helper.setText("Please see the attached document.", false);

Resource guide =
    new ClassPathResource("mail/documents/guide.pdf");

helper.addAttachment("guide.pdf", guide);

mailSender.send(message);
~~~

When the document is packaged in a JAR, its content is read from the archive and wrapped into a MIME part. The recipient gets a normal attachment without knowing whether the file originally came from the classpath or the filesystem.

### Attachment name vs. resource path

`mail/documents/guide.pdf` is the internal location in the application. `guide.pdf` is the display filename for the recipient. The two values can differ:

~~~java
helper.addAttachment(
    "user-guide-v2.pdf",
    new ClassPathResource("mail/documents/guide.pdf")
);
~~~

Never send internal paths like `BOOT-INF/classes/mail/documents/guide.pdf` to recipients. Choose a meaningful filename that exposes no server paths.

## 9. Resources must be able to open new streams

Spring's `Resource` extends `InputStreamSource`. An important property is that a standard resource like `ClassPathResource` can open a fresh stream each time `getInputStream()` is called.

~~~java
Resource logo =
    new ClassPathResource("mail/images/logo.png");

try (InputStream first = logo.getInputStream()) {
    // First read.
}

try (InputStream second = logo.getInputStream()) {
    // Open a new stream for the next read.
}
~~~

This matters when the MIME library needs to read content during message serialization or when the application inspects a resource before sending.

### Avoid InputStreamResource for single-use streams

Do not open a stream early and wrap it:

~~~java
InputStream input = resource.getInputStream();
InputStreamResource oneShot = new InputStreamResource(input);
helper.addInline("logo", oneShot, "image/png");
~~~

`InputStreamResource` wraps an already-open stream and is usually readable only once. If another step already read the stream or the library needs to reopen it, you may hit errors about a closed or exhausted stream.

For classpath resources, pass `ClassPathResource` directly:

~~~java
Resource logo =
    new ClassPathResource("mail/images/logo.png");

helper.addInline("logo", logo, "image/png");
~~~

If byte data is already loaded in memory, `ByteArrayResource` can open fresh streams from the byte array, though holding large files in RAM consumes memory. For static assets packaged inside a JAR, `ClassPathResource` is usually more suitable.

### Custom InputStreamSource

When a data source has no built-in Resource implementation, supply an `InputStreamSource` that opens a fresh stream each time:

~~~java
InputStreamSource source = () -> Files.newInputStream(path);

helper.addAttachment("report.pdf", source, "application/pdf");
~~~

This lambda opens a new file stream on each invocation. Never write a lambda that returns the same previously opened stream.

## 10. Using resources from configuration

If asset paths vary by environment, put the location in configuration:

~~~yaml
app:
  mail:
    logo: classpath:mail/images/logo.png
    terms: classpath:mail/documents/terms.pdf
~~~

Bind the configuration:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public record MailResourceProperties(
    String logo,
    String terms
) {}
~~~

Use `ResourceLoader` to resolve it:

~~~java
@Service
public class ConfiguredMailAssets {

    private final ResourceLoader resourceLoader;
    private final MailResourceProperties properties;

    public ConfiguredMailAssets(
            ResourceLoader resourceLoader,
            MailResourceProperties properties) {
        this.resourceLoader = resourceLoader;
        this.properties = properties;
    }

    public Resource logo() {
        return resourceLoader.getResource(properties.logo());
    }

    public Resource terms() {
        return resourceLoader.getResource(properties.terms());
    }
}
~~~

Default configuration can point to the classpath, while production can point to the filesystem or appropriate storage if assets need updating without rebuilding the application.

Configuration locations are inputs to the resource loader. If users authorized to edit configuration can specify URLs or file paths, restrict allowed schemes, permitted directories, and access permissions. Never accept an arbitrary location from an HTTP request and pass it straight to `ResourceLoader`; that can expose unintended files or URLs.

## 11. How do classpath resources and filesystem resources differ?

Spring has multiple `Resource` implementations. Choose the right one for where the file lives:

| Implementation | Data source | Use when |
| --- | --- | --- |
| `ClassPathResource` | Classpath, including JAR resources | Logos, templates, sample PDFs packaged with the application |
| `FileSystemResource` | Filesystem | Files created or managed by the app outside the JAR |
| `PathResource` | Java NIO Path | Working with a resolved filesystem path |
| `UrlResource` | URL | Resources over HTTP/HTTPS or another URL protocol |
| `ByteArrayResource` | In-memory byte array | Small content already in RAM |
| `InputStreamResource` | Existing InputStream | Single-use stream source; requires careful lifecycle handling |

Examples:

~~~java
Resource classpathLogo =
    new ClassPathResource("mail/images/logo.png");

Resource externalLogo =
    new FileSystemResource("/opt/app/assets/logo.png");

Resource remoteDocument =
    new UrlResource("https://cdn.example.com/docs/guide.pdf");
~~~

In a mail service, if the logo ships with the application release, use `ClassPathResource`. If administrators swap logos without redeploying, use the filesystem or object storage. If remote URLs come from untrusted data, enforce SSRF, redirect, timeout, and size protections before downloading.

### When should files live outside the JAR?

Use resources outside the JAR when:

- Administrators need to swap images/logos without rebuilding the application.
- Tenants have their own sets of images or documents.
- Files are uploaded by users and stored in object storage.
- Documents are large or updated frequently.
- Content is managed via a CMS.

Resources inside a JAR suit static assets tied to a code release, such as system logos, default templates, and fixed guide PDFs. When assets must change independently of releases, keep them outside the JAR.

## 12. Checking resources at startup and at send time

There are two verification approaches:

**Startup checks** fit mandatory assets that must always exist, such as a brand logo. The application can fail fast if the resource is missing rather than discovering it only when sending.

~~~java
@Component
public class MailAssetVerifier implements InitializingBean {

    private final Resource logo;

    public MailAssetVerifier() {
        this.logo = new ClassPathResource("mail/images/logo.png");
    }

    @Override
    public void afterPropertiesSet() throws IOException {
        if (!logo.exists() || !logo.isReadable()) {
            throw new IllegalStateException(
                "Required mail resource is missing");
        }
    }
}
~~~

**Send-time checks** fit when resources are selected dynamically per tenant, template, or notification type. Checking before constructing the message yields clear contextual errors.

Do not open a stream and hold it for the singleton's entire lifetime just to prove the file exists. Check the resource, then open streams as needed for each message.

### Checking actual content

`exists()` only tells you the resource was found. It does not prove the content is a valid PNG, an uncorrupted PDF, or the right MIME type. For static project-controlled assets, validate them in build/tests. For uploaded files or external resources, verify format and file integrity per policy.

## 13. Testing classpath resources in a test environment

Unit tests can check that resources are placed on the test/runtime classpath:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;

class MailClasspathResourceTest {

    @Test
    void logoIsAvailableOnClasspath() throws Exception {
        ClassPathResource logo =
            new ClassPathResource("mail/images/logo.png");

        assertTrue(logo.exists());
        assertTrue(logo.isReadable());

        try (InputStream input = logo.getInputStream()) {
            assertTrue(input.read() >= 0);
        }
    }
}
~~~

This test confirms the resource can be located and read on the test classpath. It does not yet prove the resource is definitely included in the final executable JAR.

### Inspecting the packaged artifact

A common mistake is tests passing in the IDE while the built artifact lacks the file due to resource filtering/excludes or custom packaging configuration.

For a JAR, you can inspect the entry list using the `jar` tool:

~~~powershell
jar tf target/my-mail-app.jar | Select-String "mail/images/logo.png"
~~~

In an executable Spring Boot JAR, the entry typically looks like:

~~~text
BOOT-INF/classes/mail/images/logo.png
~~~

In a standard Java JAR, the entry may be:

~~~text
mail/images/logo.png
~~~

Then run the application from the JAR itself and run a smoke test reading the resource. This verifies the packaged environment much closer to production than running tests solely from the IDE.

Do not hard-code physical JAR positions into application code. Entry listings are useful for artifact verification, while runtime should continue using `Resource` and the class loader.

## 14. Resource paths inside an executable Spring Boot JAR

A Spring Boot executable JAR has its own packaging layout. Application resources usually live inside `BOOT-INF/classes`, while dependency JARs live under `BOOT-INF/lib`. The Boot loader creates a class loader able to locate classes and resources inside this layout.

~~~text
my-mail-app.jar
├── META-INF/
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   ├── application.yml
    │   └── mail/
    │       └── images/
    │           └── logo.png
    └── lib/
        ├── spring-boot-*.jar
        └── jakarta-mail-*.jar
~~~

In code, still use:

~~~java
Resource logo =
    new ClassPathResource("mail/images/logo.png");
~~~

Do not use:

~~~java
new ClassPathResource(
    "BOOT-INF/classes/mail/images/logo.png"
);
~~~

`BOOT-INF/classes` is an archive packaging detail, not a prefix of classpath resource names.

### Do not assume a JAR URL protocol

Depending on Java, the Spring Boot loader, and packaging, a resource URL may have a specialized format. Do not match URL strings against `jar:file:...` or assume an archive separator always sits at a fixed position. To read content, use `Resource#getInputStream()`; if you need a URL for another API, confirm whether that API supports the protocol provided at runtime.

## 15. Common errors and troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Resource exists in IDE but missing when running JAR | File was not packaged or path is wrong | Place in `src/main/resources` and inspect JAR entries |
| `FileNotFoundException` when calling `getFile()` | Resource is inside a JAR, not a regular file | Use `getInputStream()` or pass `Resource` to the helper |
| `getResourceAsStream()` returns null | Wrong path, wrong casing, or resource not packaged | Check path from classpath root and artifact |
| Path containing `src/main/resources` is not found | Using source path instead of classpath path | Drop the source prefix; use only `mail/...` |
| Works on Windows, fails on Linux/JAR | Incorrect resource casing | Match exact file and directory names |
| Inline image does not display | Content-ID mismatch, wrong MIME type, or wrong part order | Match `cid` and `addInline`, add after `setText` |
| Broken or empty attachment | Single-read stream or already-closed resource | Use a resource that opens fresh streams |
| Resource pattern not found in dependency JARs | Using `ResourceLoader` instead of a pattern resolver or wrong pattern | Use `PathMatchingResourcePatternResolver` with `classpath*:` |
| Asset changed after deploy but app uses old version | Asset is packaged inside the JAR | Move asset to external storage if independent updates are needed |
| Using JAR URL as a filesystem path fails | Archive URL is not a File/Path | Use a stream or copy to a temp file when truly needed |

### Distinguishing path errors from file-read errors

When debugging, check in order:

1. Is the resource path correct relative to the classpath root?
2. Did the build tool copy the file into the output?
3. Is the entry present inside the final JAR?
4. Can the runtime class loader locate the resource?
5. Can `getInputStream()` read the bytes?
6. Did `MimeMessageHelper` receive the right resource, content type, and Content-ID?

Do not fix errors by switching to paths relative to the working directory when targeting resources packaged in a JAR. That makes the application dependent on launch directory and fails when running under containers or systemd.

## 16. When another API strictly requires a File or Path

Some file-processing libraries accept only `File` or `Path` instead of `Resource`. If the resource lives inside a JAR, copy the stream to a temporary file:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import org.springframework.core.io.ClassPathResource;

ClassPathResource resource =
    new ClassPathResource("mail/documents/guide.pdf");

Path temporaryFile =
    Files.createTempFile("mail-guide-", ".pdf");

try (InputStream input = resource.getInputStream()) {
    Files.copy(
        input,
        temporaryFile,
        StandardCopyOption.REPLACE_EXISTING
    );
}

// Call the library requiring a Path here.

Files.deleteIfExists(temporaryFile);
~~~

In production, use try/finally or a temp-file lifecycle abstraction to guarantee cleanup even when processing fails. For standard email-sending flows, this copy step is unnecessary because `MimeMessageHelper` already accepts `Resource`.

Do not unpack an entire JAR just to read a small logo or PDF. Create a temporary file only when an external API truly requires a filesystem path.

## 17. Managing classpath assets and external resources per environment

An application can use a default asset inside the JAR while allowing overrides with an external file upon deployment:

~~~yaml
app:
  mail:
    logo-location: classpath:mail/images/logo.png
~~~

In production, configuration can be overridden:

~~~yaml
app:
  mail:
    logo-location: file:/opt/my-app/assets/company-logo.png
~~~

The service sees only the abstraction:

~~~java
Resource logo = resourceLoader.getResource(
    mailProperties.logoLocation()
);

if (!logo.exists() || !logo.isReadable()) {
    throw new IllegalStateException("Mail logo is unavailable");
}
~~~

This decouples email-building logic from where assets are stored. However, define clear policies:

- Which default locations are allowed?
- Who has permission to change configuration?
- Are remote URLs allowed?
- Are files outside the JAR checked for permissions and content?
- When an asset changes, should the app reload or construct a fresh resource per send?
- In multi-tenant setups, which asset belongs to which tenant?

Never let an HTTP request supply an arbitrary location. Locations should come from controlled configuration or authorized asset IDs.

## 18. Takeaways for using classpath resources in emails

- Resources in `src/main/resources` are referenced from the classpath root; omit `src/main/resources` from the resource name.
- Use `ClassPathResource` or `ResourceLoader` to retrieve assets.
- For resources inside a JAR, use `getInputStream()` or pass `Resource` directly to `MimeMessageHelper`.
- Do not assume `getFile()` works; JAR entries are not ordinary filesystem files.
- For multiple resources matching a pattern, use `ResourcePatternResolver` and consider `classpath*:`.
- Match exact path casing to avoid failures when deploying to Linux.
- Resources must be re-readable when the MIME library opens streams multiple times; `ClassPathResource` is preferable to an already-opened, consumed stream.
- For inline images, Content-ID in `addInline` must match `cid:...` in HTML, and content type must be accurate.
- For attachments, the display filename is not a classpath path.
- Test both the test classpath and the actual executable JAR to catch resources excluded from the artifact.
- If an API requires a `Path`, copy the stream to a temporary file and manage cleanup; do not unpack the JAR just to read resources.
- Use in-JAR assets for static content tied to releases; use filesystem/object storage for assets needing independent updates.

In Spring Framework Mail, classpath resources allow email services to use logos, images, and sample documents without depending on the process working directory. By keeping resources as `Resource` objects from lookup through `MimeMessageHelper`, the same code runs across IDEs, classes directories, and executable JARs without assuming resources are always filesystem files.
