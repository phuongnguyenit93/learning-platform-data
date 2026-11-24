# XXE, XML Entity Expansion, and Using Safe Parsers

**Module:** Spring Security – federation  
**Parent topic:** Security Hardening  
**Technologies:** SAML 2.0, Spring Security 6.x, OpenSAML, Spring Boot 3.x, Java 17+, JAXP.

## 1. Why Is XML an Attack Surface in Federation?

In SAML 2.0, a Service Provider (SP) application receives a **SAMLResponse** via the browser and validates the **Assertion**, signature, and Identity Provider (IdP) trust. The SP also parses **IdP metadata** to locate the EntityID, KeyDescriptor, signing certificates, and endpoints. Many Spring applications also parse XML from SOAP/IAM connectors, file imports, XML Schemas, and XSLT.

An XML parser may support a **Document Type Definition (DTD)**, internal/external entities, or automatic opening of external URLs. If XML data sent by an attacker or partner is parsed without restrictions, risks include:

- **XXE (XML External Entity)**: reading local files or internal URLs that the client cannot access directly.
- **SSRF**: XML causes the backend application to send HTTP requests to private endpoints, loopback, cloud metadata, or other services.
- **Entity expansion denial of service**: recursive/nested entities cause the expanded text to be vastly larger than the input, exhausting CPU and RAM.
- **External XSD/XSLT/XInclude**: loading external resources even without declaring a DTD-style external entity.
- **Metadata URL SSRF**: the application proactively fetches metadata from an untrusted URL before parsing; this is a **different** SSRF path from XML entities.
- **Parser differentials and XML Signature Wrapping (XSW)**: the parser and the signature/element-selection logic may interpret XML differently; SAML security is not just blocking XXE.

**Mandatory principle:** Block XML risks at the **very first parsing step**, before extracting users/attributes and even before validating the SAML signature. A good signature does not make an XXE-vulnerable parser safe, because the parser must process the XML to produce objects for the signature validator.

~~~text
Browser / IdP / Partner / Metadata feed
                |
                v
HTTP body / Base64 decode / inflate (strict byte limits)
                |
                v
SECURE XML PARSER (reject DTD, external resources, XInclude)
                |
                v
SAML Protocol/Signature Validation
  Issuer, signing key, Audience, Destination, Recipient,
  InResponseTo, Conditions, SubjectConfirmation, replay
                |
                v
Approved local user mapping + tenant/resource authorization
~~~

XML accepted by the parser is **not** an authenticated SAMLResponse. An Assertion with a valid signature **does not automatically grant all business permissions**. These two boundaries must be tested separately.

## 2. DTD, Internal Entities, and External Entities

### Internal entity

XML supports defining substitution names inside a DTD:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE Hello [
  <!ENTITY team "Security Team">
]>
<Hello>Hi, &team;!</Hello>
~~~

If DTDs are allowed, the parser can expand &team; into text. Standard SAMLResponse and SAML metadata **do not require DTDs**, so the safest choice is to **reject every DOCTYPE** rather than trying to distinguish seemingly harmless DTDs.

### External general entity

~~~xml
<!DOCTYPE Document [
  <!ENTITY outside SYSTEM "file:///nonexistent/xxe-demo.txt">
]>
<Document>&outside;</Document>
~~~

This is a test example using only a **nonexistent file**, without reading real documents. If the parser resolves external entities, it can access file:// or network protocols. Resolved data can inadvertently leak into responses, audits, logs, exceptions, or downstream services.

### External DTD

~~~xml
<!DOCTYPE Document SYSTEM
  "https://example.invalid/untrusted.dtd">
<Document>Example</Document>
~~~

A parser with external DTD loading enabled can trigger a network request **merely upon encountering DOCTYPE SYSTEM**, even if the body references no specific entity.

### Parameter entities

DTDs also have **parameter entities**; they can create resolution paths beyond external general entities. Therefore, a configuration that only disables external-general-entities while forgetting external-parameter-entities and nonvalidating/load-external-dtd is insufficient.

### Entity expansion

~~~xml
<!DOCTYPE a [
  <!ENTITY x "ha">
  <!ENTITY y "&x;&x;&x;&x;">
  <!ENTITY z "&y;&y;&y;&y;">
]>
<a>&z;</a>
~~~

This is a small example illustrating the phenomenon, **not a large attack payload**. When entities are nested across many levels, the expanded text can far exceed the original XML size; **no file or HTTP access is needed** to cause DoS.

## 3. Risks by XML API

| API/mechanism | What to protect | Countermeasure |
| --- | --- | --- |
| **DocumentBuilderFactory (DOM)** | DTD, external entities, XInclude, tree RAM | disallow-doctype-decl; FSP; external-access properties; XInclude false; byte/depth limits |
| **SAXParserFactory/XMLReader** | DTD + external references | disallow DOCTYPE; disable general/parameter entities + external DTD; throwing resolver |
| **XMLInputFactory (StAX)** | DTD, external entities, token streaming | SUPPORT_DTD=false; IS_SUPPORTING_EXTERNAL_ENTITIES=false; throwing XMLResolver; DTD event policy |
| **SchemaFactory/Validator** | schemaLocation/import/include | ACCESS_EXTERNAL_SCHEMA="", ACCESS_EXTERNAL_DTD="", trusted XSD |
| **TransformerFactory/XSLT** | xsl:import/include, document() | ACCESS_EXTERNAL_STYLESHEET="", ACCESS_EXTERNAL_DTD="", trusted stylesheet |
| **XPath** | implicit parser when accepting InputSource | Parse with hardened DOM first; evaluate on Document |
| **JAXB/Unmarshaller** | internally created parser | supply hardened StAX/SAX reader; verify DTD rejection |
| **OpenSAML ParserPool** | SAMLResponse, metadata, XMLDSig DOM | Secure XML Processing Requirements per version |
| **Metadata HTTP fetch** | URL/redirect/private IP | URL allowlist, egress, DNS/IP/redirect/timeouts before XML parse |
| **XInclude** | xi:include href to file/URL | setXIncludeAware(false); check policy |
| **XMLDSig** | signed vs unsigned node selection | ID uniqueness, signature/trust validation on exact node |

**You cannot flip one switch on Spring SecurityFilterChain and assume all XML parsing is safe.** Each library and entry point has its own parser; you must inventory custom controllers, file imports, metadata resolvers, and schema/XSLT processors as well.

## 4. Parser Policy: Reject DTD and Fail Closed

For federation XML, prioritize:

1. **Reject DOCTYPE declarations** directly at the parser.
2. **FEATURE_SECURE_PROCESSING=true** on factories that support it.
3. **Disable external general entities, external parameter entities, and load-external-dtd**.
4. **ACCESS_EXTERNAL_DTD=""**, **ACCESS_EXTERNAL_SCHEMA=""**, **ACCESS_EXTERNAL_STYLESHEET=""** on the appropriate factory/API.
5. **XInclude=false**.
6. Attach an **EntityResolver/XMLResolver** that rejects external references without falling back to the default.
7. When a parser does not support a required setting, **fail closed**: never process untrusted XML using a “downgraded” factory.
8. Only parse an **app-owned InputStream** with byte limits and timeouts; never pass a user-controlled URI to parse(String).
9. Configure **resource limits** on entity count, depth, attributes, post-Base64/inflate size, and concurrency.
10. Only use **trusted** app-managed schemas/XSLT/catalogs when truly required.

| Mistake | Why is it unsafe? |
| --- | --- |
| Calling only setExpandEntityReferences(false) | External resolution/DTD may still remain; one flag is not a complete solution |
| setValidating(false) | Does not disable DTD/external entity loading |
| Enabling only FEATURE_SECURE_PROCESSING | Behavior/defaults depend on provider/JDK; set explicit external-access restrictions |
| Setting only ACCESS_EXTERNAL_DTD="" | Does not block XInclude, XSLT, external schemas, or non-DTD XML bombs |
| Regex stripping the DOCTYPE keyword | Not a standard XML parser; vulnerable to parser differentials/encoding bypasses |
| Blocking HTTP egress without blocking DTD | file:// or internal entity expansion remains a risk |
| Trusting XML because “HTTPS was used” | TLS protects transport, not XML payload safety |
| Trusting XML because “it has a signature” | The parser can be attacked before signature verification |
| Using default XML schema validation | XSD can fetch imports/includes from external URLs |
| Catching exceptions from setFeature and continuing | Insecure fallback on untrusted input |

## 5. Safe DOM with DocumentBuilderFactory in Java 17

JDK 17 provides **DocumentBuilderFactory.newDefaultNSInstance()**, selecting the JDK built-in namespace-aware DOM factory. The features below target the JDK built-in parser (Xerces derivative):

~~~java
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import org.xml.sax.SAXException;

DocumentBuilderFactory factory =
    DocumentBuilderFactory.newDefaultNSInstance();

factory.setNamespaceAware(true);
factory.setXIncludeAware(false);
factory.setExpandEntityReferences(false);
factory.setFeature(
    "http://apache.org/xml/features/disallow-doctype-decl",
    true);
factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
factory.setFeature(
    "http://xml.org/sax/features/external-general-entities",
    false);
factory.setFeature(
    "http://xml.org/sax/features/external-parameter-entities",
    false);
factory.setFeature(
    "http://apache.org/xml/features/nonvalidating/load-external-dtd",
    false);
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

DocumentBuilder builder = factory.newDocumentBuilder();
builder.setEntityResolver((publicId, systemId) -> {
    throw new SAXException("External reference forbidden");
});

// inputStream must be opened/bounded/closed by the app.
org.w3c.dom.Document document = builder.parse(inputStream);
~~~

**This is a fragment**; inputStream is not yet declared. In real code, open streams with try-with-resources, apply size/timeout bounds before parsing, and sanitize XML errors.

**The disallow-doctype-decl feature URI** is Xerces-specific; the JDK built-in parser understands it. A provider injected by a container/app server may behave differently. If unsupported, swap the provider or supply a verified equivalent hardened policy; never catch ParserConfigurationException to ignore it.

### Why shouldn't EntityResolver return null?

~~~java
builder.setEntityResolver((publicId, systemId) -> null);
~~~

**Null usually means letting the parser resolve via its default mechanism**, not denying it. For untrusted XML that does not need a DTD, a good resolver should **throw SAXException**. The resolver is only an additional layer; **disallow DOCTYPE** remains the primary defense.

### parse(String URI) is a separate SSRF vector

~~~java
// Risk if userProvidedUri is untrusted:
builder.parse(userProvidedUri);
~~~

External-access restrictions for DTDs do not prevent the application from opening the **initial XML source URI**. If the source is HTTP/metadata, the application must apply its own URL allowlist, DNS/IP/redirect controls, and egress policy, then pass a bounded InputStream to the parser.

## 6. Standalone Java 17 Hands-On Lab

The program below **compiles with plain JDK 17**, without Spring/IdP/network/file secrets. It proves **DOCTYPE is blocked even when it contains an internal entity, external file, external HTTP, or no entity at all**.

**File: XmlParserHardeningDemo.java**

~~~java
import java.io.StringReader;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;

import org.w3c.dom.Document;
import org.xml.sax.InputSource;
import org.xml.sax.SAXException;
import org.xml.sax.SAXParseException;
import org.xml.sax.helpers.DefaultHandler;

public final class XmlParserHardeningDemo {

    static DocumentBuilder safeBuilder() throws Exception {
        DocumentBuilderFactory f =
            DocumentBuilderFactory.newDefaultNSInstance();
        f.setNamespaceAware(true);
        f.setXIncludeAware(false);
        f.setExpandEntityReferences(false);
        f.setFeature(
            "http://apache.org/xml/features/disallow-doctype-decl",
            true);
        f.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        f.setFeature(
            "http://xml.org/sax/features/external-general-entities",
            false);
        f.setFeature(
            "http://xml.org/sax/features/external-parameter-entities",
            false);
        f.setFeature(
            "http://apache.org/xml/features/nonvalidating/load-external-dtd",
            false);
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        DocumentBuilder b = f.newDocumentBuilder();
        b.setEntityResolver((publicId, systemId) -> {
            throw new SAXException("No external resolution");
        });
        b.setErrorHandler(new DefaultHandler() {
            @Override
            public void error(SAXParseException e)
                    throws SAXException {
                throw e;
            }

            @Override
            public void fatalError(SAXParseException e)
                    throws SAXException {
                throw e;
            }
        });
        return b;
    }

    static String check(String xml) {
        try {
            safeBuilder().parse(
                new InputSource(new StringReader(xml)));
            return "ACCEPTED";
        } catch (Exception ex) {
            // Demo fails closed; production distinguishes
            // invalid XML (4xx) from parser config errors (5xx).
            return "BLOCKED";
        }
    }

    public static void main(String[] args) throws Exception {
        String valid =
            "<Response><Name>Alice</Name></Response>";
        Document doc = safeBuilder().parse(
            new InputSource(new StringReader(valid)));

        System.out.println("validRoot=" +
            doc.getDocumentElement().getTagName());
        System.out.println("validName=" +
            doc.getElementsByTagName("Name").item(0)
                .getTextContent());

        String internal =
            "<!DOCTYPE Response [<!ENTITY e 'TEXT'>]>" +
            "<Response><Name>&e;</Name></Response>";

        String externalFile =
            "<!DOCTYPE Response [<!ENTITY e SYSTEM " +
            "'file:///nonexistent/xxe-demo.txt'>]>" +
            "<Response><Name>&e;</Name></Response>";

        String externalHttp =
            "<!DOCTYPE Response [<!ENTITY e SYSTEM " +
            "'https://example.invalid/blocked'>]>" +
            "<Response><Name>&e;</Name></Response>";

        String emptyDoctype =
            "<!DOCTYPE Response>" +
            "<Response><Name>Alice</Name></Response>";

        System.out.println(
            "internalEntity=" + check(internal));
        System.out.println(
            "externalFile=" + check(externalFile));
        System.out.println(
            "externalHttp=" + check(externalHttp));
        System.out.println(
            "emptyDoctype=" + check(emptyDoctype));
    }
}
~~~

Run:

~~~bash
javac XmlParserHardeningDemo.java
java XmlParserHardeningDemo
~~~

**Exact expected stdout with JDK 17 built-in parser:**

~~~text
validRoot=Response
validName=Alice
internalEntity=BLOCKED
externalFile=BLOCKED
externalHttp=BLOCKED
emptyDoctype=BLOCKED
~~~

**Notes:**

- File/HTTP URLs in the example are dummy only and are not accessed if the parser blocks DOCTYPE.
- The demo checks **XML parser hardening** only, with no SAML XML Signature.
- The class uses the JDK default parser; other providers/versions must be tested accordingly.
- check() groups errors to demonstrate fail-closed behavior; in production, record metrics/config errors separately and never expose raw input/secrets.
- The program does not simulate large XML/CPU DoS; separate load/limits tests are needed.
- To verify zero real outbound I/O, use an integration-test mock HTTP server and assert **zero requests**.

## 7. SAX Parser: Using a Hardened XMLReader

SAX processes XML via events, using less RAM than DOM in many cases, but **does not prevent XXE automatically**:

~~~java
import javax.xml.XMLConstants;
import javax.xml.parsers.SAXParserFactory;
import org.xml.sax.InputSource;
import org.xml.sax.XMLReader;
import org.xml.sax.SAXException;
import org.xml.sax.helpers.DefaultHandler;

SAXParserFactory f =
    SAXParserFactory.newDefaultInstance();
f.setNamespaceAware(true);
f.setFeature(
    "http://apache.org/xml/features/disallow-doctype-decl",
    true);
f.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
f.setFeature(
    "http://xml.org/sax/features/external-general-entities",
    false);
f.setFeature(
    "http://xml.org/sax/features/external-parameter-entities",
    false);
f.setFeature(
    "http://apache.org/xml/features/nonvalidating/load-external-dtd",
    false);

XMLReader reader = f.newSAXParser().getXMLReader();
reader.setEntityResolver((publicId, systemId) -> {
    throw new SAXException("No external entities");
});
reader.setContentHandler(new DefaultHandler());
reader.parse(new InputSource(inputStream));
~~~

This is a fragment. **reader.parse** guarantees the configured resolver is used; some SAXParser.parse(source, DefaultHandler) wrappers may reassign the resolver/handler. Verify the provider and set the ACCESS_EXTERNAL_DTD property using the proper API if needed; do not treat DOM setAttribute as a SAXParserFactory API.

Do not accumulate all SAX characters() into an unbounded String and lose streaming benefits. Limit total bytes, depth, text size, and number of events.

## 8. StAX: Disable DTD/External Entities, Check DTD Events

StAX does not use FEATURE_SECURE_PROCESSING like DOM/SAX. Configuration:

~~~java
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;

XMLInputFactory f =
    XMLInputFactory.newDefaultFactory();
f.setProperty(XMLInputFactory.SUPPORT_DTD, false);
f.setProperty(
    XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
f.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
    throw new XMLStreamException("External resource forbidden");
});

XMLStreamReader reader =
    f.createXMLStreamReader(inputStream);

try {
    while (reader.hasNext()) {
        int event = reader.next();
        if (event == XMLStreamConstants.DTD) {
            throw new XMLStreamException("DOCTYPE not allowed");
        }
        // Business events: limit depth/text/count.
    }
} finally {
    reader.close();
}
~~~

**SUPPORT_DTD=false does not mean every provider always throws on DOCTYPE.** It may skip DTD processing while still emitting a DTD event. If policy requires rejecting the syntax, an explicit DTD check is necessary. Close inputStream in a separate finally/try-with-resources block; reader.close does not close the stream by default.

## 9. XSD SchemaFactory and Validator

XSD also has external imports/includes/schemaLocation. For **app-managed schemas**, forbid external references:

~~~java
import javax.xml.XMLConstants;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;
import javax.xml.transform.stream.StreamSource;

SchemaFactory sf =
    SchemaFactory.newDefaultInstance();
sf.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
sf.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
sf.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

Schema schema = sf.newSchema(
    new StreamSource(trustedSchemaStream));
Validator validator = schema.newValidator();
validator.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
validator.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

validator.validate(new StreamSource(untrustedXmlStream));
~~~

This is a fragment; streams are opened/closed by the app and byte-bounded. If using LSResourceResolver, note that **Validator does not inherit the factory resolver by default**; configure and test it on each validator per the API. Returning null from a resolver usually means default resolution. When untrusted XML is passed via StreamSource, the processor may create its own parser; consider using a hardened DOMSource/SAXSource whose parsing is controlled.

**Do not let input XML specify an XSD at a public URL and automatically download it.** Manage a trusted XSD version/catalog, validate protocol/namespace, and block xsd:import to resources outside the allowlist.

## 10. XSLT TransformerFactory

XSLT can read resources via xsl:import, xsl:include, or **document()**, independent of XXE via DTD. Compile only **trusted stylesheets**:

~~~java
import javax.xml.XMLConstants;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.stream.StreamSource;

TransformerFactory tf =
    TransformerFactory.newDefaultInstance();
tf.setFeature(
    XMLConstants.FEATURE_SECURE_PROCESSING, true);
tf.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
tf.setAttribute(
    XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");

Transformer transformer = tf.newTransformer(
    new StreamSource(trustedStylesheetStream));
transformer.transform(hardenedDomOrSaxSource, outputResult);
~~~

The fragment requires app-created inputs/output. Restrictions do not turn **untrusted XSLT** into a safe sandbox; complex expressions can still cause DoS. With an identity transform, avoid passing an untrusted StreamSource without proper parser safety.

## 11. JAXB and XPath

**JAXB:** In Java 17, JAXB is no longer bundled in the JDK. Spring Boot 3 typically uses jakarta.xml.bind with separate dependencies. Do not assume unmarshaller.unmarshal(InputStream) uses a hardened parser.

~~~java
XMLInputFactory f = XMLInputFactory.newDefaultFactory();
f.setProperty(XMLInputFactory.SUPPORT_DTD, false);
f.setProperty(
    XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
f.setXMLResolver((p, s, b, n) -> {
    throw new XMLStreamException("External URL forbidden");
});
XMLStreamReader r = f.createXMLStreamReader(untrustedStream);
try {
    Object value = unmarshaller.unmarshal(r);
} finally {
    r.close();
}
~~~

This is a fragment with an externally declared unmarshaller. If the contract forbids DOCTYPE, you need a strong enough reader/DTD-event policy **before or during JAXB consumption**; SUPPORT_DTD=false alone does not prove DOCTYPE syntax is rejected.

**XPath:** Avoid evaluate(expression, InputSource) on untrusted XML, because the XPath API may parse the source implicitly. Parse into a safe Document first, then evaluate:

~~~java
org.w3c.dom.Document doc =
    secureBuilder.parse(inputStream);
javax.xml.xpath.XPath xpath =
    javax.xml.xpath.XPathFactory
        .newDefaultInstance().newXPath();
String name = xpath.evaluate("/root/name", doc);
~~~

In SAML/XMLDSig, do not select an Assertion solely by local-name() or first element; you must select the exact signed element, namespace, and verified ID. XPath Injection is also a separate issue if expressions come from the user.

## 12. Spring Security SAML2, Saml2WebSsoAuthenticationFilter, and OpenSAML

In Spring Security 6.x, the **spring-security-saml2-service-provider** module implements SAML 2.0 based on **OpenSAML**. **Saml2WebSsoAuthenticationFilter** receives the SSO callback; the authentication provider components use OpenSAML to parse and validate the Response/Assertion and then create a Saml2Authentication per the trusted **RelyingPartyRegistration**.

~~~java
@Bean
SecurityFilterChain security(HttpSecurity http)
        throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/error").permitAll()
            .anyRequest().authenticated())
        .saml2Login(Customizer.withDefaults());
    return http.build();
}
~~~

This is a **snippet** requiring imports and a configured repository. The goal is to use the **framework authentication pipeline**, rather than manually parsing SAMLResponse with DOM in a controller and reading NameID from unverified XML.

### OpenSAML ParserPool

OpenSAML has a parser pool mechanism and **Secure XML Processing Requirements**. If building or replacing **BasicParserPool**, ensure version alignment:

- expandEntityReferences=false;
- FEATURE_SECURE_PROCESSING=true;
- disallow-doctype-decl=true;
- XInclude must not be allowed external access;
- coalescing and ignoreComments must match OpenSAML DOM/signature expectations;
- do not enable external entity processing to “fix XML signature errors”.

**Spring Security 6.5** can select OpenSAML 4/5 components depending on dependency versions. OpenSAML 4 and 5 differ in packages/APIs; do not copy parser configuration from **Spring Security SAML Extension/OpenSAML 2** to newer versions as if they were identical.

Read docs for the **exact version** and integrate tests: XXE external resolution must be blocked, while XMLDSig canonicalization/signature validation still works properly.

### XXE differs from XML Signature Wrapping (XSW)

~~~text
SAML Response
    +-- Assertion A: signed, subject=alice
    +-- Assertion B: unsigned, subject=administrator
~~~

If the signature validator verifies **A** while code selects **B** to build the principal, that is an **XML Signature Wrapping/ID-selection error**, not XXE. You must verify that the signed reference matches the exact element, XML IDs are unique, signature trust and issuer/audience/conditions pass, and **consume the exact validated object**; never reparse and pick an arbitrary Assertion.

**Two independent layers:** A parser blocking DTDs does not verify SAML signatures. A valid SAML signature also does not disable external entity resolution if the parser already ran before verification.

## 13. Metadata Fetch and IdP Trust

IdP metadata may be loaded via an admin-configured URL. If a UI allows arbitrary URL input, the server can issue requests to loopback/private IPs or be redirected to an internal endpoint **before the XML parser is invoked**. This is metadata URL SSRF.

Minimum policy:

1. Metadata sources may only be created by trusted admin/partner onboarding.
2. HTTPS URL allowlist; TLS certificate/hostname verification; redirect limits.
3. DNS/IP checks and egress deny for loopback, link-local, and out-of-policy private zones; DNS rebinding defense per threat model.
4. HTTP timeouts, Content-Length/body/decompressed size limits, and concurrency quota.
5. Hardened XML parser when consuming the InputStream.
6. Verify IdP EntityID, KeyDescriptor, signing certificates, and endpoints/roles per contract.
7. Metadata signature/trusted signing certificate or transport provenance per policy; do not trust a new key just because current metadata advertises it.
8. validUntil/cacheDuration/refresh/last-known-good within valid trust lifetime; audit IdP key/issuer changes.
9. Do not log raw metadata/signing data/sensitive PII.
10. Do not allow logging-in users to specify an arbitrary IdP metadata endpoint.

**ACCESS_EXTERNAL_DTD="" does not protect the initial metadata URL fetch**, because that is an outbound request proactively made by the app's HTTP client.

## 14. Resource Limits for XML Even Without DTD

An XML document without DOCTYPE can still contain huge numbers of nodes, deep nesting, attributes, Base64 text, or CPU-heavy XSD/XPath/XSLT. Java JAXP provides **JDK-specific processing limits**:

| Property | Limit Type |
| --- | --- |
| **jdk.xml.entityExpansionLimit** | Number of entity expansions |
| **jdk.xml.totalEntitySizeLimit** | Total entity size |
| **jdk.xml.maxGeneralEntitySizeLimit** | General entity size |
| **jdk.xml.maxParameterEntitySizeLimit** | Parameter entity size |
| **jdk.xml.elementAttributeLimit** | Number of attributes |
| **jdk.xml.maxElementDepth** | XML depth |
| **jdk.xml.maxOccurLimit** | Schema repetition count |
| **jdk.xml.xpathExprGrpLimit** | Number of expression groups |
| **jdk.xml.xpathTotalOpLimit** | Total XPath operations |

A JDK built-in DOM-specific example:

~~~java
factory.setAttribute("jdk.xml.entityExpansionLimit", "1000");
factory.setAttribute("jdk.xml.totalEntitySizeLimit", "100000");
factory.setAttribute("jdk.xml.maxElementDepth", "100");
~~~

**Numbers are illustrative only** and must be calibrated against valid payloads. These are implementation properties, not portable across every parser; if unsupported, do not silently ignore. If the protocol forbids DTDs, rejecting DOCTYPE remains the foundational control.

**Multi-layered controls:**

- Request size limits at reverse proxy/Servlet container (including chunked).
- Base64-decoded SAMLResponse limit, decompression/inflation limit.
- Streaming body bounds before loading an entire byte[].
- Parser depth/attribute/text/entity limits, CPU timeout/concurrency.
- Metadata maximum descriptors/certificate count; XML validation/XPath/XSLT complexity.
- Audit sanitized parser errors and outbound attempts, without storing raw SAML Assertion/NameID/tokens.

Blocking external URLs does not prevent CPU DoS; blocking DTDs also does not stop oversized documents. **Do not wait for OutOfMemoryError and catch it to recover.**

## 15. Spring Boot 3 XML Data Endpoint: Do Not Break the SAML Filter

If the SP has a separate XML import API alongside the SAML callback, the controller must use a hardened parser. Do not parse SAMLResponse in a custom controller and treat it as login.

**src/main/java/com/example/xml/SafeXmlParser.java**

~~~java
package com.example.xml;

import java.io.ByteArrayInputStream;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import org.xml.sax.SAXException;

public final class SafeXmlParser {

    private static final int MAX_BYTES = 262_144;

    public Document parse(byte[] body) throws Exception {
        if (body == null || body.length == 0
                || body.length > MAX_BYTES) {
            throw new IllegalArgumentException(
                "XML body size forbidden");
        }

        DocumentBuilderFactory f =
            DocumentBuilderFactory.newDefaultNSInstance();
        f.setNamespaceAware(true);
        f.setXIncludeAware(false);
        f.setExpandEntityReferences(false);
        f.setFeature(
            "http://apache.org/xml/features/disallow-doctype-decl",
            true);
        f.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        f.setFeature(
            "http://xml.org/sax/features/external-general-entities",
            false);
        f.setFeature(
            "http://xml.org/sax/features/external-parameter-entities",
            false);
        f.setFeature(
            "http://apache.org/xml/features/nonvalidating/load-external-dtd",
            false);
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        DocumentBuilder builder = f.newDocumentBuilder();
        builder.setEntityResolver((publicId, systemId) -> {
            throw new SAXException("No external XML references");
        });
        return builder.parse(new ByteArrayInputStream(body));
    }
}
~~~

**src/main/java/com/example/xml/XmlInspectController.java**

~~~java
package com.example.xml;

import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/xml")
public class XmlInspectController {

    private final SafeXmlParser parser = new SafeXmlParser();

    @PostMapping(
        path = "/inspect",
        consumes = MediaType.APPLICATION_XML_VALUE)
    public Map<String, String> inspect(@RequestBody byte[] body)
            throws Exception {
        var doc = parser.parse(body);
        return Map.of(
            "root", doc.getDocumentElement().getTagName());
    }
}
~~~

**Not a complete application**: the project also needs a Boot main class, dependencies, and a **SecurityFilterChain** authenticating/authorizing /api/xml/inspect. The 262,144-byte limit is checked **after** the HTTP body has become a byte[], so **reverse proxy/container request-size limits before the body enters RAM** are also required. Invalid XML errors return sanitized 400, parser config errors return safe 5xx; never return raw XML. Large SAML metadata requires a different policy limit.

## 16. Negative Test Suite for Federation XXE

Use authorized local/staging test environments, a mock HTTP server, and dummy file paths. Never attempt to exfiltrate real files or scan production private networks.

| # | Case | Expected |
| --- | --- | --- |
| 1 | Simple XML without DOCTYPE | Parses, but is not yet SAML authenticated |
| 2 | Internal DTD/entity | Reject DOCTYPE |
| 3 | External general entity file:///nonexistent/... | Reject; do not read file |
| 4 | External HTTP entity to mock URL | Reject; mock request count = 0 |
| 5 | External parameter entity | Reject before resolution |
| 6 | External DTD SYSTEM URL | Zero outbound requests |
| 7 | Empty DOCTYPE | Reject per DTD prohibition policy |
| 8 | Nested entity expansion (small “Billion Laughs” sample) | Reject before expansion |
| 9 | XInclude href=file:///... | Do not open file |
| 10 | schemaLocation to remote URL | Do not fetch XSD |
| 11 | External xsd:import/include | ACCESS_EXTERNAL_SCHEMA blocks |
| 12 | External xsl:import/include | ACCESS_EXTERNAL_STYLESHEET blocks |
| 13 | External XSLT document() | Do not load external document |
| 14 | StAX SUPPORT_DTD=false encountering DOCTYPE | DTD event detected/rejected per contract |
| 15 | SAX resolver null fallback | Test detects resolution risk |
| 16 | Parser provider does not support security feature | Fail closed, no fallback defaults |
| 17 | App parse(userControlledURI) | Reject untrusted initial URL |
| 18 | Metadata URL localhost/private IP | HTTP client policy blocks before parse |
| 19 | Metadata redirect to private IP | Blocked per hop/egress policy |
| 20 | Large XML after Base64 decode | Reject at decoded body limit |
| 21 | Excessively inflating compressed payload | Reject at inflate limit |
| 22 | XML nested thousands of levels deep | Depth/resource limit rejects |
| 23 | Element with excessive attributes | Attribute limit rejects |
| 24 | Invalid encoding/malformed XML | Do not parse; safe 4xx error |
| 25 | Fake namespace mimicking SAML tags | Fails SAML trust validation |
| 26 | Duplicate XML ID/signature wrapping | Reject or use exact signed element |
| 27 | XML accepted by parser but SAML unsigned | Authentication fails |
| 28 | SAML signed but wrong Audience/Issuer | Authentication fails |
| 29 | Expired IdP metadata | Do not trust expired metadata |
| 30 | IdP metadata signing key changed out of policy | Trust check fails |
| 31 | Unauthenticated XML import endpoint | SecurityFilterChain denies before parsing |
| 32 | JAXB differs from XMLInputFactory policy | Test exact provider/Unmarshaller |
| 33 | Parser logs raw SAMLResponse/NameID | Redact |
| 34 | Multi-request XML DoS | Quota/timeout keeps system stable |
| 35 | Third-party JAXP parser override | Features still enforced or fail closed |

### Testing with a mock server

1. Create an internal test mock HTTP server and a request counter.
2. Send XML with an external reference pointing to the mock endpoint to the **exact application/route doing the parsing**.
3. Assert the parser rejects and the mock server **receives 0 requests**.
4. Assert errors contain no raw XML, sensitive file paths, or credentials.
5. Repeat across DOM, SAX, StAX, XSD, XSLT/JAXB, and OpenSAML metadata paths actually used by the app.
6. For identity flows, additionally test issuer/signature/audience/conditions and signed-element selection.
7. When changing JDK, parser provider, or OpenSAML, re-run the regression suite.

**Do not mock an always-succeeding Authentication and conclude SAML security is tested.** Testing parser XXE and testing signature/trust are two independent test suites.

## 17. Quick Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| DOCTYPE rejected by parser | Safe XML policy is working | Do not enable DTD just to parse |
| ParserConfigurationException | Provider does not support feature | Fail closed; switch parser/provider |
| XML still fetches external DTD | Missing disallow-doctype/load-external-dtd/resolver | Inspect factory/reader, throw in resolver |
| XInclude still opens files | setXIncludeAware not disabled | Disable and test |
| StAX does not throw on DOCTYPE | SUPPORT_DTD=false only disables processing | Reject DTD event per contract |
| XSD validator fetches URL automatically | ACCESS_EXTERNAL_SCHEMA not set | Use trusted schema/catalog |
| XSLT calls document() URL | ACCESS_EXTERNAL_STYLESHEET not set | Trusted stylesheet + deny |
| XPath code bypasses safe DOM parser | evaluate(InputSource) parses implicitly | Evaluate on hardened Document |
| DOM blocks XXE but metadata still SSRFs | Untrusted initial HTTP URL | Safe fetch/egress allowlist |
| App OOMs on XML without DTD | Missing input/depth/concurrency limits | Hard resource quotas |
| OpenSAML signature fails after custom ParserPool | Coalescing/comments/canonicalization changed | Follow Secure XML Processing Requirements |
| SAML signs Assertion A but app uses B | XML Signature Wrapping | Validate ID/ref, use signed object |
| XML parses cleanly but auth fails | Wrong issuer/audience/signature/trust | Debug SAML policy, do not remove parser hardening |
| Logs contain XML and secrets | Error handler/APM body logging | Redact and do not echo input |

Processing order: identify XML source → limit bytes → identify actual parser → DTD/external settings → XInclude/XSD/XSLT → initial metadata fetch → test zero outbound → SAML trust → local authorization. Do not fix errors by disabling FEATURE_SECURE_PROCESSING or allowing arbitrary file/HTTP resolution.

## 18. Production Checklist

- [ ] Inventory every XML entry point: SAMLResponse, metadata, XML import, SOAP, XSD/XSLT/JAXB.
- [ ] **Reject DOCTYPE** for federation XML that does not require DTDs.
- [ ] DOM/SAX: FSP=true; general/parameter entities false; external DTD false; external access denied.
- [ ] StAX: SUPPORT_DTD=false; external entities false; XMLResolver deny; reject DTD event when contract forbids DOCTYPE.
- [ ] XInclude disabled; no file/HTTP resolution from untrusted input.
- [ ] SchemaFactory/Validator deny external DTD/SCHEMA and use trusted XSD.
- [ ] TransformerFactory denies external DTD/STYLESHEET; do not run untrusted XSLT.
- [ ] JAXB receives a hardened reader; XPath evaluates only on a hardened DOM.
- [ ] Parser not supporting a required setting → **fail closed**, no fallback.
- [ ] Never use parse(String URI) with user input; metadata fetch requires URL/DNS/redirect/egress policy.
- [ ] Limit HTTP body, Base64/DEFLATE decoded bytes, depth, attributes, CPU/time/concurrency.
- [ ] Mock HTTP test confirms XXE payloads make zero network requests.
- [ ] OpenSAML ParserPool matches exact version and Secure XML Processing Requirements.
- [ ] XMLDSig verifies the exact signed element/ID, rejecting signature wrapping/duplicate IDs.
- [ ] SAML trust: Issuer, trusted certificate, Audience, Destination/Recipient, Conditions, InResponseTo, replay.
- [ ] Metadata EntityID, signing key, validUntil/cacheDuration, and refresh policy are verified.
- [ ] All XML API endpoints are authenticated/authorized and never echo raw XML.
- [ ] Errors/logs/APM never leak SAML Assertion, NameID, private keys, or file contents.
- [ ] JDK/OpenSAML/Spring Security/XML providers are patched; regression tests run after upgrades.
- [ ] Local account/tenant/resource authorization still applies after SAML authentication.

**Conclusion:** In SAML federation, **XML parsing is an attack surface before authentication evidence exists**. For XML that does not need DTDs, **reject DOCTYPE**, block external resources across all parsers/validators/transformers, bound resources, and **fail closed** if a setting does not work. Only then verify XMLDSig/SAML protocol and enforce application authorization; never treat clean parser output as proof of a valid user.

## 19. References

- [OWASP XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): DOM, SAX, StAX, XSD, XSLT, XPath, JAXB, and fail-closed.
- [Oracle JDK 17 JAXP Security Guide](https://docs.oracle.com/en/java/javase/17/security/java-api-xml-processing-jaxp-security-guide.html): FEATURE_SECURE_PROCESSING, ACCESS_EXTERNAL_*, JDK resource limits.
- [Java 17 DocumentBuilderFactory API](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/parsers/DocumentBuilderFactory.html): parser features, XInclude, entity expansion.
- [Spring Security 6.5 OpenSAML Support](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/opensaml.html): OpenSAML 4/5 integration.
- [Spring Security 6.5 SAML2 Login](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html): SAML authentication pipeline.
- [OpenSAML Secure XML Processing Requirements](https://shibboleth.atlassian.net/wiki/spaces/OSAML/pages/1828356995/Secure+XML+Processing+Requirements): parser security, comments/coalescing, and XMLDSig.
- [Spring Blog – SAML XML Parser Security](https://spring.io/blog/2018/03/01/spring-security-saml-and-this-week-s-saml-vulnerability/): unsafe ParserPool configurations.
- [CWE-611 XXE](https://cwe.mitre.org/data/definitions/611.html): XML External Entity Reference.
- [CWE-776 XML Entity Expansion](https://cwe.mitre.org/data/definitions/776.html): Recursive Entity References in DTDs.
